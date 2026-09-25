# Gerador de NF-e ABI

MVP para montar, validar e assinar XML da NF-e ABI versão 1.00 com base no pacote
`PL_NFeABI_1.00` deste repositório.

O projeto também contém o **XSD XML Builder**, uma aplicação genérica que seleciona
uma pasta de schemas e gera modelos XML sem depender de um JSON ou XML previamente
preparado. A geração genérica é estrutural; regras fiscais que não estão expressas no
XSD continuam pertencendo ao perfil específico da NF-e ABI.

O montador é **XSD-first**: o JSON pode ter os campos em qualquer ordem. A ordem final
das tags, escolhas e cardinalidades é obtida diretamente dos schemas. Regras que
dependem de mais de um campo são tratadas por um validador de negócio separado.

## Estado atual

Implementado:

- leitura recursiva de `xs:include`;
- montagem da raiz `NFeABI` a partir de JSON;
- sequências, escolhas, atributos e grupos repetidos;
- cálculo da chave de acesso de 44 posições, `cDV` e `infNFeABI/@Id`;
- validações básicas de CPF, CNPJ, homologação, contingência, substituição e totais;
- validação pelo `NFeABI_v1.00.xsd`;
- XML compacto em UTF-8, sem identação entre as tags;
- assinatura enveloped XMLDSig com C14N, RSA-SHA1 e SHA-1, conforme o MOC;
- validação criptográfica local da assinatura gerada;
- validação estrutural de rascunhos ainda não assinados.

Ainda depende de fontes oficiais externas ao repositório:

- tabelas de modalidade, natureza, espécie, instrumento, CST e `cClassTrib`;
- indicadores associados ao CST e ao `cClassTrib`;
- URLs oficiais e regra completa do QR Code;
- códigos `tpEvento` de pagamento de parcela e apropriação de créditos;
- WSDLs e endereços dos ambientes de autorização.

Por isso, o exemplo completo incluído é adequado para testar estrutura e assinatura, mas não
deve ser considerado uma nota autorizável sem a confirmação dessas tabelas.

O exemplo padrão usa `tpNF=1` e contempla todos os grupos aplicáveis ao cenário de
operação imobiliária completa adotado como referência: declarante, endereços,
participação, cadastro detalhado do imóvel, autorização de XML, redutores, pagamento,
totalização e informações adicionais. Campos exclusivos de outros cenários, como
substituição, contingência, permuta e incorporação/loteamento, não podem ser somados ao
mesmo XML sem violar regras condicionais; devem ser representados por modelos próprios.

O exemplo completo usa `tpAmb=1` exclusivamente para viabilizar o teste estrutural local e
contém nomes claramente sintéticos. **Ele não deve ser transmitido.** Há uma
inconsistência no pacote v1.00a: o literal exigido pelo MOC para `xNome` em
homologação possui 62 caracteres, enquanto o XSD limita `xNome` a 60. O gerador não
trunca esse valor nem modifica o schema oficial; uma definição corrigida deve ser
obtida antes dos testes reais de homologação.

## Instalação

No diretório `XsdXmlBuilder - JonasBrother`:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

No macOS, instale Python 3.11 ou superior com suporte a Tkinter e execute no Terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m tkinter
python -m xsd_model_builder
```

`python -m tkinter` deve abrir uma janela de teste. A interface do gerador é aberta
por `python -m xsd_model_builder`.

Também é possível executar diretamente pelo código-fonte:

```powershell
$env:PYTHONPATH = "src"
python -m nfeabi_generator --help
```

## Gerar um rascunho sem assinatura

```powershell
$env:PYTHONPATH = "src"
python -m nfeabi_generator build `
  --input examples/nfeabi-completa.json `
  --output output/nfeabi-modelo-completo.xml `
  --unsigned
```

O rascunho não contém uma assinatura falsa. Para validar o restante da estrutura, a
aplicação usa uma assinatura temporária apenas em memória.

## Gerar XML assinado

Defina a senha do PFX em variável de ambiente para que ela não apareça no histórico:

```powershell
$env:NFEABI_PFX_PASSWORD = "senha-do-certificado"
$env:PYTHONPATH = "src"
python -m nfeabi_generator build `
  --input examples/nfeabi-completa.json `
  --output output/nfeabi-assinada.xml `
  --pfx C:\certificados\emitente.pfx
```

O certificado deve possuir uma chave privada RSA. O MVP ainda não valida cadeia
ICP-Brasil, LCR, OIDs de CNPJ/CPF ou autorização cadastral do emitente; essas
verificações continuam sendo realizadas pelo autorizador.

## Validar um XML existente

```powershell
$env:PYTHONPATH = "src"
python -m nfeabi_generator validate --xml output/nfeabi-assinada.xml
```

Para um rascunho sem `Signature`:

```powershell
python -m nfeabi_generator validate `
  --xml output/nfeabi-modelo-completo.xml `
  --allow-unsigned
```

## Convenções do JSON

- atributos usam prefixo `@`, por exemplo `@versao` e `@nTransmit`;
- grupos repetidos usam arrays;
- códigos, documentos e decimais devem ser strings para preservar zeros e escala;
- campos opcionais vazios devem ser omitidos, não enviados como `null` ou `""`;
- `ide/cDV` e `infNFeABI/@Id` podem ser omitidos, pois são calculados;
- `Signature` não deve ser enviada no JSON;
- `qrCode` e `urlChave` ainda precisam ser fornecidos pela aplicação chamadora.

O arquivo [`examples/nfeabi-completa.json`](examples/nfeabi-completa.json) é o modelo
padrão e demonstra o contrato completo do cenário principal. O arquivo
[`examples/nfeabi-minimal.json`](examples/nfeabi-minimal.json) foi mantido apenas para
comparação e testes exploratórios; não deve ser usado como referência funcional.

## Gerador genérico por XSD

Para abrir a interface gráfica pelo código-fonte:

```powershell
$env:PYTHONPATH = "src"
python -m xsd_model_builder
```

Na interface:

1. selecione a pasta que contém os XSDs;
2. escolha o XSD raiz e o elemento global raiz;
3. mantenha o modo **Completo** para incluir os elementos opcionais compatíveis;
4. escolha quantos exemplos criar para grupos repetíveis;
5. gere e valide o XML.

O arquivo de saída é sugerido em `Modelos XML Gerados`, na raiz do projeto,
independentemente da pasta dos XSDs. No aplicativo macOS empacotado, o padrão é
`~/Documents/Modelos XML Gerados`, fora do pacote `.app`. O botão **Salvar como…**
permite escolher outra pasta; essa escolha permanece ao trocar o elemento raiz.

Cada `xs:choice` aceita somente uma alternativa. O campo “Alternativa choice” define
qual ramo será usado, começando em 1. O gerador informa no log quais ramos foram
omitidos. `xs:any` e regras externas ao XSD também são apresentados como avisos.

Uso equivalente pela linha de comando:

```powershell
$env:PYTHONPATH = "src"
python -m xsd_model_builder `
  --schema '.\SVRS Oficiais\NFeABI\PL_NFeABI_1.00\PL_NFeABI_1.00\NFeABI_v1.00.xsd' `
  --root NFeABI `
  --mode complete
```

Sem `--output`, a linha de comando também usa `Modelos XML Gerados`. Informe
`--output C:\outra-pasta\modelo.xml` no Windows ou
`--output ~/Documents/modelo.xml` no macOS para escolher outro local.

## Criar o executável Windows

Execute no PowerShell:

```powershell
.\build-exe.ps1
```

O script cria um ambiente isolado, instala as dependências de compilação e produz
`dist\XsdXmlBuilder.exe`. O executável não contém schemas fixos: a pasta dos XSDs é
selecionada pelo usuário em cada execução.

## Criar o aplicativo macOS

No Terminal de um Mac com Python 3.11 ou superior e Tkinter:

```bash
bash build-mac.sh
open "dist/XSD XML Builder - By Jonatas Oliveira.app"
```

O script cria um ambiente isolado em `.build-venv-macos`, instala as dependências e
gera `dist/XSD XML Builder - By Jonatas Oliveira.app`. Para escolher outro Python,
use, por exemplo, `PYTHON_BIN=python3.13 bash build-mac.sh`. O aplicativo não inclui
XSDs: selecione a pasta dos schemas ao abrir a interface. O build usa a arquitetura do Python no Mac
em que foi executado; para Macs Intel e Apple Silicon, gere e teste as versões
correspondentes. O `.exe` do Windows não executa no macOS.

Para distribuir o `.app` a outros usuários, assine e notarize o aplicativo com a
Apple após testar o build no Mac.

## Testes

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

No macOS, com o ambiente `.venv` ativado, execute
`python -m unittest discover -s tests -v`.

Os testes incluem geração de certificado temporário, assinatura, validação XSD e
verificação criptográfica. Nenhum certificado real é necessário.

## Validar XML existente e verificar uma pasta

Depois de selecionar a pasta e o XSD raiz na interface, clique em **Validar XML existente…**
e escolha o arquivo XML. O programa mostra os erros de linha e de estrutura retornados
pelo próprio XSD. Para testar todas as raízes documentais da pasta, use **Verificar pasta XSD…**;
o relatório JSON registra o modo, a alternativa de `xs:choice` e o erro de cada caso.

Na linha de comando:

```powershell
$env:PYTHONPATH = "src"
python -m xsd_model_builder --schema C:\schemas\nfe_v4.00.xsd --xml C:\xml\nota.xml
python -m xsd_model_builder.conformance_cli C:\schemas --report C:\relatorios\conformidade.json
```

## Matriz SVRS

O manifesto [`portal-svrs-sources.json`](portal-svrs-sources.json) relaciona os pacotes
oficiais publicados em `Documentos` e os diretórios operacionais `/Schemas/` do portal
SVRS. Para baixar os pacotes, guardar os ZIPs com seus hashes e executar a matriz:

```powershell
$env:PYTHONPATH = "src"
python -m xsd_model_builder.portal_conformance --sync --operational --check
```

Os resultados ficam em `CONFORMIDADE-SVRS.md` e
`CONFORMIDADE-SVRS.json`, na raiz do projeto. O relatório só aprova o conjunto quando todos os casos
selecionados passam. O teste cobre a gramática XSD das versões baixadas; valores fiscais
reais, regras de negócio, assinatura digital e autorização na SEFAZ requerem validações
próprias do modelo e do cenário. Pacotes com `xs:any` obrigatório e `strict` sem declarar
o conteúdo externo são indicados como inconclusivos, nunca aprovados automaticamente.
