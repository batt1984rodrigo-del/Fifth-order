# Contrato do Fifth Order móvel para o TCRIA

## Finalidade

O Fifth Order móvel é um módulo derivado, externo e não autorizativo. Ele observa o JSON oficial
concluído do TCRIA, cria um checkpoint para cada gate publicado, explica por que registrou sua
avaliação complementar e encadeia recibos SHA-256. Ele não altera o TCRIA, não recalcula seus gates
e não promove sinais ou resultados oficiais.

## Fronteira operacional

```text
repositório e execução TCRIA              repositório Fifth Order
┌──────────────────────────┐             ┌────────────────────────────┐
│ documentos -> gates      │             │ leitura do JSON oficial    │
│ -> JSON oficial imutável ├────────────>│ -> checkpoints derivados   │
└──────────────────────────┘             │ -> cadeia + relatórios     │
                                         └────────────────────────────┘
```

O único hand-off é o artefato oficial. O módulo não segue caminhos documentais presentes no JSON,
não abre os documentos originais e não importa código do TCRIA.

## Momento da observação

Na versão atual do TCRIA, os gates são calculados em memória e persistidos juntos no bundle final.
Assim, o modo correto é `post_bundle_reconstruction`: o Fifth Order reconstrói a ordem contratual
dos checkpoints após o JSON ficar disponível. Observação interna em tempo real exigiria um evento
ou hook no produtor, que não faz parte do contrato atual e não foi adicionado.

## Ordem reconstruída

1. `prescriptiveGate`
2. `complianceGate`
3. `traceabilityCheck`
4. `maturityGate`
5. `ledgerRuntimeCheck`

Gates futuros são preservados depois desses cinco, em ordem lexical, e recebem avaliação
complementar `conditional`, salvo um `BLOCKED`, que continua `blocked`.
Depois de qualquer bloqueio em um documento, todos os checkpoints seguintes desse mesmo documento
permanecem `blocked`; o status oficial de origem continua registrado sem alteração.

## Cadeia de custódia derivada

1. O JSON lido de arquivo recebe SHA-256 dos bytes exatos.
2. O payload interpretado recebe outro SHA-256 por serialização canônica
   `quinta_ordem_json_v1`.
3. O genesis vincula sessão, fonte, escopo, modo, horário e contagens.
4. O primeiro checkpoint aponta para o genesis.
5. Cada checkpoint aponta para o recibo anterior.
6. `receipt_sha256` é o SHA-256 do checkpoint canônico sem o próprio recibo.
7. `final_chain_sha256` aponta para o último recibo ou para o genesis quando não há gates.

O verificador detecta alteração de conteúdo, remoção, inserção, duplicação, reordenação, quebra de
sequência, troca de sessão, fonte ou autoridade e divergência do recibo final.

## Conteúdo de um checkpoint

- partição e índice do registro no bundle oficial;
- referência e SHA-256 documental já publicados pelo TCRIA;
- classificação e motivos oficiais;
- nome, status, motivo e lastro do gate oficial;
- status, motivo e resumo complementar do Fifth Order;
- exigência de revisão humana;
- recibo anterior e recibo atual.

O campo `document.text` nunca integra o checkpoint. `source_evidence=None` é válido porque o motivo
oficial obrigatório já explica o resultado do gate.

## Regras fail-closed

O módulo recusa, antes de publicar qualquer relatório:

- JSON inválido, UTF-8 inválido, chave duplicada, `NaN` ou infinito;
- razão de gate ausente ou vazia;
- SHA-256 documental inválido ou conflitante entre o registro e `document`;
- registro `raises_accusation=true` sem gates;
- ausência de um dos cinco gates do contrato TCRIA atual em registro acusatório;
- divergência entre as listas publicadas e `total_files_scanned` ou `accusation_set_count`;
- divergência entre a coleção publicada e o campo `raises_accusation` do registro;
- estrutura oficial incompatível com o contrato observado;
- cadeia alterada;
- destino de saída dentro da raiz do artefato-fonte, inclusive por symlink.

Status oficial desconhecido não é normalizado nem apagado: fica preservado em `source_status`, e o
Fifth Order registra `blocked` como avaliação complementar.

## Artefatos produzidos

```text
<output>/<session-id-seguro>/
├── <session>_fifth_order_mobile.json
├── <session>_fifth_order_mobile.md
├── <session>_checkpoints.jsonl
└── <session>_manifest.json
```

O manifesto é publicado por último. Uma sessão idêntica pode ser reutilizada byte a byte; conteúdo
diferente com o mesmo identificador não sobrescreve a trilha anterior.
