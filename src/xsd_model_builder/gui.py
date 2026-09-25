from __future__ import annotations

import threading
from pathlib import Path
from tkinter import BooleanVar, IntVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .errors import XsdModelError
from .conformance import run_conformance
from .generator import GenerationOptions, XsdModelGenerator
from .paths import default_output_directory, suggested_output_path
from .schema import SchemaCandidate, XsdCatalog, discover_schemas, format_qname
from .validator import validate_xml


COMPLETE_MODE = "Completo — inclui opcionais compatíveis"
MINIMAL_MODE = "Mínimo — somente obrigatórios"


class XsdXmlBuilderApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("XSD XML Builder - By Jonatas Oliveira")
        self.root.geometry("880x650")
        self.root.minsize(760, 560)

        self.folder_var = StringVar()
        self.schema_var = StringVar()
        self.root_element_var = StringVar()
        self.output_var = StringVar(value=str(default_output_directory() / "modelo-completo.xml"))
        self.mode_var = StringVar(value=COMPLETE_MODE)
        self.repeat_var = IntVar(value=1)
        self.choice_var = IntVar(value=1)
        self.validate_var = BooleanVar(value=True)
        self.status_var = StringVar(value="Selecione uma pasta que contenha arquivos XSD.")

        self._candidates: list[SchemaCandidate] = []
        self._candidate_by_display: dict[str, SchemaCandidate] = {}
        self._build_layout()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)

        title = ttk.Label(frame, text="Gerador genérico de XML por XSD", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        subtitle = ttk.Label(
            frame,
            text="O modo completo inclui todos os elementos opcionais compatíveis e uma alternativa de cada xs:choice.",
        )
        subtitle.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

        ttk.Label(frame, text="Pasta dos XSDs:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(frame, textvariable=self.folder_var).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Button(frame, text="Selecionar…", command=self._browse_folder).grid(row=2, column=2, padx=(8, 0), pady=5)

        ttk.Label(frame, text="XSD raiz:").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=5)
        self.schema_combo = ttk.Combobox(frame, textvariable=self.schema_var, state="readonly")
        self.schema_combo.grid(row=3, column=1, columnspan=2, sticky="ew", pady=5)
        self.schema_combo.bind("<<ComboboxSelected>>", self._schema_selected)

        ttk.Label(frame, text="Elemento raiz:").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=5)
        self.root_combo = ttk.Combobox(frame, textvariable=self.root_element_var, state="readonly")
        self.root_combo.grid(row=4, column=1, columnspan=2, sticky="ew", pady=5)
        self.root_combo.bind("<<ComboboxSelected>>", self._suggest_output)

        ttk.Label(frame, text="Modo:").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=5)
        mode_combo = ttk.Combobox(
            frame,
            textvariable=self.mode_var,
            state="readonly",
            values=(COMPLETE_MODE, MINIMAL_MODE),
        )
        mode_combo.grid(row=5, column=1, sticky="ew", pady=5)

        controls = ttk.Frame(frame)
        controls.grid(row=5, column=2, sticky="e", padx=(8, 0), pady=5)
        ttk.Label(controls, text="Repetições:").grid(row=0, column=0, padx=(0, 4))
        ttk.Spinbox(controls, from_=1, to=20, textvariable=self.repeat_var, width=4).grid(row=0, column=1)
        ttk.Label(controls, text="  Alternativa choice:").grid(row=0, column=2, padx=(8, 4))
        ttk.Spinbox(controls, from_=1, to=20, textvariable=self.choice_var, width=4).grid(row=0, column=3)

        ttk.Label(frame, text="Arquivo de saída:").grid(row=6, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(frame, textvariable=self.output_var).grid(row=6, column=1, sticky="ew", pady=5)
        ttk.Button(frame, text="Salvar como…", command=self._browse_output).grid(row=6, column=2, padx=(8, 0), pady=5)

        ttk.Checkbutton(
            frame,
            text="Validar o XML gerado contra o XSD raiz",
            variable=self.validate_var,
        ).grid(row=7, column=1, sticky="w", pady=(5, 10))

        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.generate_button = ttk.Button(actions, text="Gerar XML", command=self._start_generation)
        self.generate_button.grid(row=0, column=1, sticky="e")
        self.validate_button = ttk.Button(actions, text="Validar XML existente…", command=self._start_validation)
        self.validate_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.check_button = ttk.Button(actions, text="Verificar pasta XSD…", command=self._start_conformance)
        self.check_button.grid(row=0, column=3, sticky="e", padx=(8, 0))

        self.log = ScrolledText(frame, height=14, wrap="word", font=("Consolas", 9), state="disabled")
        self.log.grid(row=9, column=0, columnspan=3, sticky="nsew")

    def _browse_folder(self) -> None:
        selected = filedialog.askdirectory(title="Selecione a pasta que contém os XSDs")
        if not selected:
            return
        self.folder_var.set(selected)
        self._scan_folder()

    def _scan_folder(self) -> None:
        try:
            self._candidates = discover_schemas(Path(self.folder_var.get()))
        except XsdModelError as exc:
            messagebox.showerror("Erro ao ler XSDs", str(exc), parent=self.root)
            return

        with_roots = [item for item in self._candidates if item.global_elements]
        self._candidate_by_display = {item.display_name: item for item in with_roots}
        displays = list(self._candidate_by_display)
        self.schema_combo["values"] = displays
        if displays:
            self.schema_var.set(displays[0])
            self._schema_selected()
        self.status_var.set(
            f"{len(self._candidates)} XSD(s) encontrado(s); "
            f"{len(with_roots)} contém elemento raiz."
        )
        self._write_log(f"Pasta carregada: {self.folder_var.get()}")

    def _schema_selected(self, _event: object | None = None) -> None:
        candidate = self._candidate_by_display.get(self.schema_var.get())
        roots = list(candidate.global_elements) if candidate else []
        self.root_combo["values"] = roots
        self.root_element_var.set(roots[0] if roots else "")
        self._suggest_output()

    def _suggest_output(self, _event: object | None = None) -> None:
        if not self.root_element_var.get():
            return
        self.output_var.set(
            str(suggested_output_path(self.root_element_var.get(), self.output_var.get()))
        )

    def _browse_output(self) -> None:
        current = self.output_var.get().strip()
        selected = filedialog.asksaveasfilename(
            title="Salvar modelo XML",
            defaultextension=".xml",
            filetypes=(("Arquivo XML", "*.xml"), ("Todos os arquivos", "*.*")),
            initialdir=str(Path(current).parent if current else default_output_directory()),
            initialfile=(
                f"{self.root_element_var.get()}-modelo-completo.xml"
                if self.root_element_var.get()
                else "modelo-completo.xml"
            ),
        )
        if selected:
            self.output_var.set(selected)

    def _start_generation(self) -> None:
        candidate = self._candidate_by_display.get(self.schema_var.get())
        root_name = self.root_element_var.get().strip()
        output_text = self.output_var.get().strip()
        if candidate is None or not root_name or not output_text:
            messagebox.showwarning(
                "Dados incompletos",
                "Selecione a pasta, o XSD raiz, o elemento raiz e o arquivo de saída.",
                parent=self.root,
            )
            return

        try:
            repeat_count = max(int(self.repeat_var.get()), 1)
            choice_index = max(int(self.choice_var.get()) - 1, 0)
        except (ValueError, TypeError):
            messagebox.showwarning("Valor inválido", "Repetições e alternativa devem ser números.", parent=self.root)
            return

        self.generate_button.configure(state="disabled")
        self.status_var.set("Gerando e validando…")
        self._write_log(f"\nSchema raiz: {candidate.path}")
        self._write_log(f"Elemento raiz: {root_name}")
        options = GenerationOptions(
            include_optional=self.mode_var.get() == COMPLETE_MODE,
            repeat_count=repeat_count,
            choice_index=choice_index,
            validate=self.validate_var.get(),
        )
        thread = threading.Thread(
            target=self._generate_worker,
            args=(candidate.path, root_name, Path(output_text), options),
            daemon=True,
        )
        thread.start()

    def _start_validation(self) -> None:
        candidate = self._candidate_by_display.get(self.schema_var.get())
        if candidate is None:
            messagebox.showwarning(
                "Schema não selecionado",
                "Selecione a pasta e o XSD raiz correspondente ao XML.",
                parent=self.root,
            )
            return
        selected = filedialog.askopenfilename(
            title="Selecione o XML para validar",
            filetypes=(("Arquivo XML", "*.xml"), ("Todos os arquivos", "*.*")),
        )
        if not selected:
            return
        xml_path = Path(selected)
        self.validate_button.configure(state="disabled")
        self.status_var.set("Validando XML…")
        self._write_log(f"\nValidando arquivo: {xml_path}")
        self._write_log(f"Contra o XSD: {candidate.path}")
        threading.Thread(
            target=self._validate_worker,
            args=(candidate.path, xml_path),
            daemon=True,
        ).start()

    def _validate_worker(self, schema_path: Path, xml_path: Path) -> None:
        try:
            qname = validate_xml(schema_path, xml_path)
            self.root.after(0, self._validation_succeeded, xml_path, qname)
        except Exception as exc:
            self.root.after(0, self._validation_failed, exc)

    def _validation_succeeded(self, xml_path: Path, qname: tuple[str, str]) -> None:
        self.validate_button.configure(state="normal")
        self.status_var.set("XML válido para o XSD selecionado.")
        self._write_log(f"VALIDAÇÃO OK: {xml_path}")
        self._write_log(f"Raiz: {format_qname(qname)}")
        messagebox.showinfo("Validação concluída", f"XML válido para o XSD selecionado:\n{xml_path}", parent=self.root)

    def _validation_failed(self, exc: Exception) -> None:
        self.validate_button.configure(state="normal")
        self.status_var.set("XML inválido ou schema não compilável.")
        self._write_log(f"VALIDAÇÃO FALHOU: {exc}")
        messagebox.showerror("Falha na validação", str(exc), parent=self.root)

    def _start_conformance(self) -> None:
        folder = Path(self.folder_var.get().strip())
        if not folder.is_dir():
            messagebox.showwarning("Pasta não selecionada", "Selecione uma pasta de XSDs.", parent=self.root)
            return
        output = filedialog.asksaveasfilename(
            title="Salvar relatório de conformidade",
            defaultextension=".json",
            initialfile="conformidade-xsd.json",
            filetypes=(("Relatório JSON", "*.json"),),
        )
        if not output:
            return
        self.check_button.configure(state="disabled")
        self.status_var.set("Verificando todas as raízes XSD…")
        self._write_log(f"\nVerificando pasta: {folder}")
        threading.Thread(
            target=self._conformance_worker,
            args=(folder, Path(output)),
            daemon=True,
        ).start()

    def _conformance_worker(self, folder: Path, output: Path) -> None:
        try:
            report = run_conformance(folder)
            report.write_json(output)
            self.root.after(0, self._conformance_finished, report, output)
        except Exception as exc:
            self.root.after(0, self._conformance_failed, exc)

    def _conformance_finished(self, report: object, output: Path) -> None:
        self.check_button.configure(state="normal")
        self.status_var.set(
            f"Verificação: {report.passed} OK, {report.failed} falhas, {report.skipped} ignorados."
        )
        self._write_log(f"Relatório: {output}")
        self._write_log(self.status_var.get())
        for case in report.cases:
            if case.status == "failed":
                self._write_log(
                    f"FALHA: {case.schema} :: {case.root} :: {case.mode} "
                    f"choice {case.choice}: {case.message}"
                )
        if report.failed:
            messagebox.showwarning(
                "Incompatibilidades encontradas",
                f"{report.failed} caso(s) falharam. Veja o relatório:\n{output}",
                parent=self.root,
            )
        else:
            messagebox.showinfo(
                "Verificação concluída",
                f"{report.passed} casos passaram. Relatório:\n{output}",
                parent=self.root,
            )

    def _conformance_failed(self, exc: Exception) -> None:
        self.check_button.configure(state="normal")
        self.status_var.set("Não foi possível verificar a pasta.")
        self._write_log(f"VERIFICAÇÃO FALHOU: {exc}")
        messagebox.showerror("Falha na verificação", str(exc), parent=self.root)

    def _generate_worker(
        self,
        schema_path: Path,
        root_name: str,
        output: Path,
        options: GenerationOptions,
    ) -> None:
        try:
            catalog = XsdCatalog(schema_path)
            result = XsdModelGenerator(catalog, options).generate(root_name)
            output = output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(result.xml_bytes())
            self.root.after(0, self._generation_succeeded, output, result)
        except Exception as exc:  # A thread devolve qualquer erro para a interface.
            self.root.after(0, self._generation_failed, exc)

    def _generation_succeeded(self, output: Path, result: object) -> None:
        self.generate_button.configure(state="normal")
        self.status_var.set("XML gerado com sucesso.")
        self._write_log(f"Arquivo criado: {output}")
        self._write_log(f"Raiz: {format_qname(result.root_qname)}")
        self._write_log(f"Validação XSD: {'OK' if result.validated else 'não executada'}")
        for warning in result.warnings:
            self._write_log(f"AVISO: {warning}")
        action = "criado e validado" if result.validated else "criado"
        messagebox.showinfo("Concluído", f"Modelo XML {action}:\n{output}", parent=self.root)

    def _generation_failed(self, exc: Exception) -> None:
        self.generate_button.configure(state="normal")
        self.status_var.set("Não foi possível gerar o XML.")
        self._write_log(f"ERRO: {exc}")
        messagebox.showerror("Falha na geração", str(exc), parent=self.root)

    def _write_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main() -> None:
    root = Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except Exception:
        pass
    XsdXmlBuilderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
