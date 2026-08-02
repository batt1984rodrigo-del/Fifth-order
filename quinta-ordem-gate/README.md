# Quinta Ordem Gate

Meta-gate determinístico de qualidade e precisão informacional para sistemas de IA.

O projeto recebe um `ExecutionContext`, verifica requisitos objetivos e produz uma decisão
auditável. Ele não altera evidências, não substitui gates anteriores e não transforma confiança
numérica em certeza da verdade.

## Escopo do MVP

- núcleo independente de modelo, fornecedor e domínio;
- validação fail-closed do contrato de entrada;
- verificações de integridade, rastreabilidade, suporte probatório, coerência e resolução;
- preservação monotônica de qualquer bloqueio anterior;
- JSON e Markdown consolidados, um relatório por finding e manifesto SHA-256;
- adaptador TCRIA opcional e isolado;
- revisão humana obrigatória para resultados não aprovados.

Não há integração OpenAI, agente, análise emocional ou leitura direta de documentos neste MVP.

## Invariantes

1. Evidências originais nunca são modificadas.
2. Verificadores recebem snapshots independentes do contexto.
3. Qualquer gate anterior `blocked` determina `BLOCKED`, independentemente de médias.
4. Falha estrutural, falha de plugin ou verificador obrigatório ausente falha de modo fechado.
5. Requisito não avaliado não conta como requisito satisfeito.
6. Cada finding possui código, severidade, explicação, ponto e encaminhamento próprios.
7. Relatórios são derivados, usam nomes seguros e não podem ser gravados em raízes de evidência.
8. O adaptador TCRIA importa o núcleo; o núcleo nunca importa o TCRIA.
9. A decisão é vinculada ao `ExecutionContext` exato por SHA-256; outro contexto é rejeitado,
   ainda que reutilize o mesmo `execution_id`.

## Arquitetura

```text
src/quinta_ordem/
├── models.py                 # contrato e tipos do domínio
├── validation.py             # validação estrutural do ExecutionContext
├── serialization.py          # JSON estrito e determinístico
├── confidence.py             # confiança por requisitos verificáveis
├── gate.py                   # orquestração e decisão fail-closed
├── reporting.py              # bundle derivado e manifesto SHA-256
├── adapters/
│   └── tcria.py              # adaptador puro e opcional
└── verifiers/
    ├── base.py               # interface Verifier
    ├── registry.py           # registro ordenado e extensível
    ├── integrity.py
    ├── traceability.py
    ├── evidence.py
    ├── consistency.py
    └── resolution.py
```

Fluxo de avaliação:

```text
ExecutionContext
  -> validação do contrato
  -> snapshot independente por verificador
  -> findings explicativos
  -> breakdown de confiança
  -> decisão monotônica
  -> bundle derivado + manifesto
```

## Contrato de integração

`ExecutionContext` possui os seguintes campos obrigatórios:

| Campo | Tipo | Finalidade |
| --- | --- | --- |
| `execution_id` | `str` não vazia | identidade estável da execução |
| `evidence` | `list[dict]` | metadados das evidências originais |
| `artifacts` | `list[dict]` | artefatos derivados conhecidos |
| `gate_results` | `list[dict]` | resultados de gates anteriores |
| `logs` | `list[dict]` | registros estruturados da execução |
| `decisions` | `list[dict]` | fatos, hipóteses, sinais ou recomendações |
| `metadata` | `dict` | inclui `open_points` e, opcionalmente, `evidence_roots` |

Evidência mínima verificável:

```python
{
    "artifact_id": "EVD-001",
    "sha256": "<64 caracteres hexadecimais>",
    "modified_original": False,
    "source": "memory://case/evidence-001",
}
```

Decisão mínima verificável:

```python
{
    "decision_id": "DEC-001",
    "classification": "fact",
    "support_level": "direct",
    "evidence_refs": ["EVD-001"],
    "promoted": False,
}
```

Classificações reconhecidas: `fact`, `hypothesis`, `allegation`, `signal` e
`recommendation`. Suportes reconhecidos: `direct`, `corroborated`, `partial`,
`unsupported`, `none` e `unknown`.

O gate opera somente sobre o contrato recebido. Um SHA-256 declarado é validado por formato e
coerência entre referências, mas o núcleo não abre o arquivo original para recalcular o hash.
Essa responsabilidade pertence à ingestão e à cadeia de custódia do sistema produtor.

## Estados

- `APPROVED`: todos os requisitos obrigatórios aplicáveis foram executados e satisfeitos.
- `CONDITIONAL`: há warning, informação ou incerteza formal que exige revisão humana.
- `RETURNED`: existe falha alta ou cobertura insuficiente que deve voltar para correção.
- `BLOCKED`: existe falha crítica, bloqueio anterior, contrato inválido ou falha obrigatória.

Um bloqueio anterior nunca é apagado por resultado posterior, mesmo quando a lista contém
resultados duplicados ou conflitantes.

## Confiança verificável

A confiança não estima a verdade. Ela resume requisitos avaliados e satisfeitos em cinco
dimensões:

| Dimensão | Peso |
| --- | ---: |
| integridade | 25% |
| rastreabilidade | 20% |
| suporte probatório | 25% |
| coerência lógica | 20% |
| resolução | 10% |

Uma dimensão não executada começa em zero. Findings reduzem somente a dimensão correspondente;
um finding crítico zera essa dimensão e determina `BLOCKED` antes de qualquer média.

## Uso

```python
from hashlib import sha256

from quinta_ordem import ExecutionContext, QuintaOrdemGate

context = ExecutionContext(
    execution_id="case-001",
    evidence=[
        {
            "artifact_id": "EVD-001",
            "sha256": sha256(b"registered-evidence").hexdigest(),
            "modified_original": False,
            "source": "memory://case/evidence-001",
        }
    ],
    artifacts=[],
    gate_results=[{"gate": "prior-gate", "status": "approved"}],
    logs=[],
    decisions=[
        {
            "decision_id": "DEC-001",
            "classification": "fact",
            "support_level": "direct",
            "evidence_refs": ["EVD-001"],
            "promoted": False,
        }
    ],
    metadata={"open_points": []},
)

decision = QuintaOrdemGate.default().evaluate(context)
print(decision.status.value, decision.confidence)
```

## Relatórios derivados

Use a operação única de bundle para aplicar a proteção de caminhos e publicar o manifesto por
último:

```python
from pathlib import Path

from quinta_ordem.reporting import write_report_bundle

bundle = write_report_bundle(decision, context, Path("output"))
print(bundle.manifest)
```

Cada bundle contém:

```text
output/<execution-id-seguro>/
├── <execution-id-seguro>_quinta_ordem.json
├── <execution-id-seguro>_quinta_ordem.md
├── points/
│   └── 001_<point-id-seguro>.md
└── <execution-id-seguro>_manifest.json
```

O manifesto lista caminho relativo, tipo, MIME type, tamanho e SHA-256 dos bytes efetivamente
gravados. Ele não inclui a si próprio. Repetir uma execução idêntica reutiliza o bundle byte a
byte; conteúdo divergente com o mesmo `execution_id` falha sem sobrescrever o anterior.
O JSON, o Markdown e o manifesto registram `execution_context_sha256`; o escritor confirma esse
vínculo antes de publicar qualquer arquivo.

Para proteger originais, informe caminhos absolutos em `source_path`, `original_path`, `path` ou
`source`, ou declare raízes explicitamente:

```python
metadata = {
    "open_points": [],
    "evidence_roots": ["/absolute/path/to/original-evidence"],
}
```

## Verificadores extensíveis

```python
from quinta_ordem import Finding, Severity, Verifier


class DomainVerifier(Verifier):
    name = "domain_rule"

    def verify(self, context):
        return [
            Finding(
                verifier=self.name,
                code="DOMAIN_REVIEW",
                severity=Severity.WARNING,
                message="Revisão de domínio necessária.",
                point_id="domain-001",
            )
        ]


gate = QuintaOrdemGate.default()
gate.register_verifier(DomainVerifier())
```

Nomes duplicados são rejeitados. A ordem de registro é a ordem de execução. Exceções ou retorno
inválido de um plugin são convertidos em finding crítico auditável.

## Adaptador TCRIA

O adaptador é importado explicitamente e não depende do pacote TCRIA:

```python
from quinta_ordem.adapters.tcria import TCRIAExecutionContextAdapter

context = TCRIAExecutionContextAdapter().adapt(tcria_payload)
```

Contrato normalizado aceito (todos os campos-base abaixo são obrigatórios):

- `quinta_ordem_adapter_version`: deve ser `"1.0"`;
- `execution_id`;
- listas `evidence`, `artifacts`, `gate_results`, `logs` e `decisions`;
- `metadata`, contendo `open_points`, ou `open_points` na raiz, nunca nos dois locais;
- opcional `signals_for_verification`, com `signal_id` obrigatório.

Sinais são convertidos em `classification="signal"`, permanecem `promoted=False` e geram ponto
aberto para revisão humana. Hash ausente, preservação não declarada e status desconhecido não são
preenchidos por suposição. O payload recebido é copiado profundamente e permanece inalterado.
Contextos não serializáveis, origens relativas ou ambíguas e estruturas inválidas são recusados
antes da escrita do bundle; não há relatório parcial nem conversão implícita para texto.

## Instalação e validação

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
python examples/demo.py
```

O demo gera JSON consolidado, Markdown consolidado, um relatório por finding e manifesto em
`output/demo/`.
