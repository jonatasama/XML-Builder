# Conformidade estrutural dos XSDs SVRS

Verificação: 2026-09-24T20:42:02-03:00.
Fontes catalogadas no [portal SVRS](https://dfe-portal.svrs.rs.gov.br/) em 2026-09-24.

A coluna OK indica geração e validação XSD dos casos mínimo, completo e das alternativas
de `xs:choice` testadas. Regras fiscais externas ao XSD, assinatura e autorização
pelo ambiente SEFAZ exigem testes específicos adicionais.

Nos diretórios operacionais, as raízes testadas são as versões atuais listadas
em `portal-svrs-sources.json`; arquivos antigos presentes no mesmo diretório não
são contados como um único pacote de versão.

| Família | Fonte | XSDs | Raízes testadas | Casos OK | Falhas | Situação |
|---|---|---:|---:|---:|---:|---|
| BPe | [PL_BPe_100b_NT2026.002 RTC_1.01](https://dfe-portal.svrs.rs.gov.br/Bpe/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_BPe_100b_NT2026.002%20RTC_1.01.zip) | 27 | 20 | 78 | 0 | Aprovado |
| CTe | [PL_CTe_400_NT2026.001 RTC_VincPgto_1.01c_corr_2](https://dfe-portal.svrs.rs.gov.br/Cte/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_CTe_400_NT2026.001%20RTC_VincPgto_1.01c_corr_2.zip) | 46 | 40 | 206 | 0 | Aprovado |
| CTe | [PL_CTe_400_NT2026.002 RTC_1.01_corr_2](https://dfe-portal.svrs.rs.gov.br/Cte/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_CTe_400_NT2026.002%20RTC_1.01_corr_2.zip) | 46 | 40 | 206 | 0 | Aprovado |
| MDFe | [PL_MDFe_300b_NT012025_1.04](https://dfe-portal.svrs.rs.gov.br/Mdfe/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_MDFe_300b_NT012025_1.04.zip) | 41 | 32 | 87 | 1 | Incompatível / inconclusivo |
| NF3e | [PL_NF3E_1.00a_NT2026.002 RTC_1.01](https://dfe-portal.svrs.rs.gov.br/Nf3e/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_NF3E_1.00a_NT2026.002%20RTC_1.01.zip) | 23 | 16 | 53 | 0 | Aprovado |
| NFCom | [PL_NFCOM_1.00_NT2026.002 RTC_1.01](https://dfe-portal.svrs.rs.gov.br/Nfcom/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_NFCOM_1.00_NT2026.002%20RTC_1.01.zip) | 20 | 14 | 46 | 0 | Aprovado |
| NFe-NFCe | [PL_010b_NT2025_002_v1.30](https://dfe-portal.svrs.rs.gov.br/Nfe/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_010b_NT2025_002_v1.30.zip) | 5 | 2 | 24 | 0 | Aprovado |
| NFe-NFCe | [Eventos_RTC](https://dfe-portal.svrs.rs.gov.br/Nfe/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=Eventos_RTC.zip) | 18 | 17 | 34 | 0 | Aprovado |
| NFe-NFCe | [Schema_Evento_211110_NT2025.002 v1.40](https://dfe-portal.svrs.rs.gov.br/Nfe/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=Schema_Evento_211110_NT2025.002%20v1.40.zip) | 1 | 1 | 2 | 0 | Aprovado |
| ONE | [PL_ONE_v200e_1.00](https://dfe-portal.svrs.rs.gov.br/One/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_ONE_v200e_1.00.zip) | 13 | 10 | 36 | 0 | Aprovado |
| DCe | [PL_DCe_v1.00a_NT2024.001v1.00](https://dfe-portal.svrs.rs.gov.br/Dce/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_DCe_v1.00a_NT2024.001v1.00.zip) | 22 | 14 | 45 | 0 | Aprovado |
| DCe | [PL_DCe_100_BT2024.001_SVD_v1.00](https://dfe-portal.svrs.rs.gov.br/Dce/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_DCe_100_BT2024.001_SVD_v1.00.zip) | 6 | 4 | 16 | 0 | Aprovado |
| PES | [PL_DFePAA_102](https://dfe-portal.svrs.rs.gov.br/Pes/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_DFePAA_102.zip) | 7 | 4 | 12 | 0 | Aprovado |
| NFAg | [PL_NFAg_NT2026.002 RTC_1.01](https://dfe-portal.svrs.rs.gov.br/Nfag/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_NFAg_NT2026.002%20RTC_1.01.zip) | 21 | 14 | 40 | 0 | Aprovado |
| NFeABI | [PL_NFeABI_1.00](https://dfe-portal.svrs.rs.gov.br/Nfabi/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_NFeABI_1.00.zip) | 20 | 14 | 39 | 0 | Aprovado |
| NFGas | [PL_NFGas_NT2026.002 RTC_1.01](https://dfe-portal.svrs.rs.gov.br/Nfgas/DownloadArquivoEstatico/?tipoArquivo=2&nomeArquivo=PL_NFGas_NT2026.002%20RTC_1.01.zip) | 20 | 14 | 52 | 0 | Aprovado |
| BPe | [operational-PRBPE](https://dfe-portal.svrs.rs.gov.br/Schemas/PRBPE/) | 35 | 3 | 18 | 0 | Aprovado |
| CTe | [operational-PRCTE](https://dfe-portal.svrs.rs.gov.br/Schemas/PRCTE/) | 323 | 11 | 82 | 0 | Aprovado |
| NF3e | [operational-PRNF3E](https://dfe-portal.svrs.rs.gov.br/Schemas/PRNF3E/) | 37 | 1 | 8 | 0 | Aprovado |
| NFCom | [operational-PRNFCOM](https://dfe-portal.svrs.rs.gov.br/Schemas/PRNFCOM/) | 25 | 1 | 7 | 0 | Aprovado |
| NFAg | [operational-PRNFAG](https://dfe-portal.svrs.rs.gov.br/Schemas/PRNFAG/) | 20 | 1 | 5 | 0 | Aprovado |
| NFGas | [operational-PRNFGAS](https://dfe-portal.svrs.rs.gov.br/Schemas/PRNFGAS/) | 20 | 1 | 9 | 0 | Aprovado |
| NFe-NFCe | [operational-PRNFE](https://dfe-portal.svrs.rs.gov.br/Schemas/PRNFE/) | 268 | 1 | 22 | 0 | Aprovado |
| DCe | [operational-PRDCE](https://dfe-portal.svrs.rs.gov.br/Schemas/PRDCE/) | 17 | 1 | 5 | 0 | Aprovado |

## Falhas e pendências

### MDFe: PL_MDFe_300b_NT012025_1.04

- `PL_MDFe_300b_NT012025_1.05/retMDFeConsultaDFe_v3.00.xsd / retMDFeConsultaDFe`: Não foi possível materializar o elemento obrigatório 'procMDFe': xs:any obrigatório com processContents='strict' não identifica qual declaração global deve ocupar o conteúdo.

## Áreas do portal sem XSD de documento próprio publicado

- [NFF](https://dfe-portal.svrs.rs.gov.br/Nff/Documentos): Portal da Nota Fiscal Fácil: não há pacote XSD próprio na página Documentos.
- [DIFAL](https://dfe-portal.svrs.rs.gov.br/Difal/Documentos): Portal de cálculo/consulta do DIFAL: não há pacote XSD próprio na página Documentos.
- [CFF](https://dfe-portal.svrs.rs.gov.br/Cff/Documentos): Portal Conformidade Fácil: validador e tabelas; não há pacote XSD próprio na página Documentos.

Observação: o menu do portal chama a nota de energia elétrica de **NF3e**. A grafia
'NFPSe' da imagem foi tratada como referência a essa área do portal.

Os ZIPs originais e seus hashes SHA-256 estão em `SVRS Oficiais` e
`CONFORMIDADE-SVRS.json`. Quando um ZIP oficial omite um XSD necessário,
a dependência usada de outro ZIP oficial fica registrada no relatório JSON.
