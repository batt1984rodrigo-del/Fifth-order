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
- modo móvel externo para reconstruir checkpoints de bundles oficiais concluídos do TCRIA;
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
├── mobile/
│   ├── tcria.py               # observador externo e cadeia de recibos
│   ├── models.py             # sessão e checkpoints imutáveis
│   └── reporting.py          # JSON, JSONL, Markdown e manifesto
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

## Cenários demonstráveis

O exemplo `examples/scenarios.py` executa os quatro resultados possíveis usando contextos
pequenos e reproduzíveis:

| Cenário | Resultado esperado | Motivo operacional |
| --- | --- | --- |
| resultado íntegro e resolvido | `APPROVED` | nenhum requisito pendente |
| ponto aberto | `CONDITIONAL` | exige revisão humana |
| gate anterior devolvido | `RETURNED` | a correção deve ocorrer na origem |
| original modificado | `BLOCKED` | a cadeia de custódia impede a promoção |

Execute:

```bash
python examples/scenarios.py
```

Cada cenário valida o estado esperado e grava seu próprio bundle em `output/scenarios/`. Se uma
alteração futura produzir um estado diferente, o exemplo termina com erro em vez de apresentar
uma demonstração incorreta.

## Integração demonstrável com o TCRIA

O exemplo `examples/tcria_integration.py` mostra o hand-off normalizado completo:

```text
payload TCRIA
  -> TCRIAExecutionContextAdapter
  -> ExecutionContext destacado do payload original
  -> QuintaOrdemGate
  -> decisão + bundle + manifesto SHA-256
```

Execute:

```bash
python examples/tcria_integration.py
```

O payload contém um fato suportado e um sinal ainda pendente. O adaptador preserva o sinal sem
promoção, cria um ponto de revisão humana e o gate retorna `CONDITIONAL`. O exemplo também confirma
que o payload original do TCRIA não foi modificado e grava o bundle em `output/tcria/`.

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

## Fifth Order móvel para o TCRIA

O modo móvel acompanha o TCRIA como módulo externo. O TCRIA permanece em seu próprio repositório e
não é importado, alterado ou chamado pelo Fifth Order:

```text
TCRIA inalterado
  -> JSON oficial concluído
  -> FifthOrderMobileGate
  -> checkpoint por gate + resumo do porquê
  -> cadeia SHA-256 + JSONL + relatório + manifesto
```

O observador conserva separadamente:

- `source_status`, `source_reason` e `source_evidence`, exatamente como publicados pelo TCRIA;
- `companion_status`, `companion_reason` e `companion_summary`, próprios do Fifth Order;
- SHA-256 dos bytes do JSON oficial e SHA-256 do payload canônico;
- recibo genesis, sequência e vínculo `previous_receipt_sha256` em cada checkpoint;
- autoridade `complementary_non_authoritative` e escopo `custody_and_explanation_only`.

Mapeamento complementar, sem modificar o estado oficial:

| Estado TCRIA | Estado Fifth Order | Leitura do módulo móvel |
| --- | --- | --- |
| `PASS` | `approved` | observação formal preservada; não é aprovação do mérito |
| `WARN` | `conditional` | atenção e revisão humana |
| `BLOCKED` | `blocked` | bloqueio preservado sem promoção |
| `NOT_EVALUATED` | `conditional` | requisito não avaliado não conta como satisfeito |
| `NOT_APPLICABLE` | `conditional` | limitação oficial mantida explícita |
| desconhecido | `blocked` | falha fechada, preservando o texto de origem |

O mapeamento é monotônico dentro de cada documento: depois de um checkpoint `blocked`, os
checkpoints posteriores continuam `blocked`, embora o `source_status` de cada gate permaneça
inalterado.

Uso externo:

```bash
python -m quinta_ordem.mobile \
  /caminho/para/auditoria_oficial_tcria.json \
  --output /caminho/externo/fifth-order-output \
  --producer-revision <commit-tcria-quando-conhecido>
```

Ou pela API:

```python
from pathlib import Path

from quinta_ordem.mobile import FifthOrderMobileGate, write_mobile_report_bundle

session = FifthOrderMobileGate().observe_bundle_file(
    Path("/caminho/para/auditoria_oficial_tcria.json"),
    producer_revision="<commit conhecido>",
)
reports = write_mobile_report_bundle(session, Path("/caminho/externo/fifth-order-output"))
print(reports.manifest)
```

O output contém JSON da sessão, ledger JSONL com um registro pequeno por gate, Markdown legível e
manifesto dos arquivos derivados. `document.text` e os sinais extensos do TCRIA não são copiados.
Registros oficiais sem gates são enumerados, mas o Fifth Order não inventa checkpoints ausentes.
As contagens oficiais e a presença dos cinco gates atuais são validadas para impedir que um bundle
truncado seja apresentado como trilha completa.

Limite declarado: o TCRIA atual calcula os gates em memória e os publica somente no JSON final.
Por isso, este modo usa `observation_mode="post_bundle_reconstruction"`; ele acompanha cada gate
publicado assim que o bundle fica disponível, mas não afirma observação interna em tempo real.
Uma cadeia de hashes detecta alterações quando o recibo final é preservado fora da própria cadeia;
ela não é assinatura digital nem prova autônoma de autoria do TCRIA.

## Instalação e validação

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
python examples/demo.py
python examples/scenarios.py
python examples/tcria_integration.py
python -m quinta_ordem.mobile --help
```

O demo gera JSON consolidado, Markdown consolidado, um relatório por finding e manifesto em
`output/demo/`.
