# Testes dos pacotes já presentes no repositório

Execução em 24/09/2026 com o gerador atual, em modos mínimo e completo e nas
alternativas de `xs:choice` testadas. Cada XML gerado foi validado pelo XSD raiz.

| Pasta | XSDs | Raízes | Casos aprovados | Falhas |
|---|---:|---:|---:|---:|
| NFe ABI / PL_NFeABI_1.00 | 20 | 14 | 39 | 0 |
| NFSE LOCACAO | 30 | 18 | 611 | 0 |
| NFe Modelo 55 | 22 | 12 | 73 | 0 |
| CTe | 46 | 40 | 206 | 0 |
| DCe | 22 | 14 | 45 | 0 |

Os detalhes de cada caso estão nos arquivos JSON nesta pasta. A NFSe de locação
foi testada como pacote local; ela não é uma das famílias do portal SVRS usado
na matriz oficial.
