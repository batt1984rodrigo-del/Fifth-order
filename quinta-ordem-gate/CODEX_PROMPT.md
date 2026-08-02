# Missão para o Codex

Você está trabalhando no repositório `quinta-ordem-gate`.

## Contexto

O projeto implementa uma camada independente de garantia de qualidade e precisão
informacional para sistemas de IA. Ele deve funcionar como um meta-gate transversal:
consome um `ExecutionContext`, examina integridade, rastreabilidade, suporte probatório,
coerência, resolução e resultados de gates anteriores, e produz uma decisão auditável.

O produto é voltado à indústria de IA. O TCRIA será usado posteriormente como
implementação de referência, mas o núcleo não pode depender dele.

## Regras invariáveis

1. Nunca modificar evidências originais.
2. Operar somente sobre metadados, cópias de trabalho e artefatos derivados.
3. Nunca sobrescrever um bloqueio de gate anterior.
4. Falhas críticas não podem ser compensadas por média.
5. Cada finding deve gerar um registro explicativo próprio.
6. A confiança representa requisitos verificáveis satisfeitos, não certeza absoluta da verdade.
7. O núcleo deve permanecer agnóstico de modelo, fornecedor e domínio.
8. Não adicionar emoção, análise afetiva ou conteúdo do último documento discutido.

## Tarefa inicial

1. Inspecione todo o repositório.
2. Execute `pytest`.
3. Corrija erros encontrados sem alterar os princípios acima.
4. Adicione:
   - validação robusta do `ExecutionContext`;
   - serialização segura de enums e dataclasses;
   - relatório Markdown consolidado;
   - manifesto de execução com hashes dos relatórios derivados;
   - interface `Verifier` extensível e registro de verificadores;
   - adaptador inicial `TCRIAExecutionContextAdapter`, isolado em `adapters/tcria.py`;
   - testes para cadeia de custódia, bloqueio anterior, decisões sem evidência,
     pontos não resolvidos e geração de relatórios.
5. Não integrar API OpenAI ainda.
6. Não criar agente ainda.
7. Entregar um MVP determinístico, testável e documentado.

## Critérios de conclusão

- Todos os testes passam.
- `python examples/demo.py` gera:
  - JSON consolidado;
  - Markdown consolidado;
  - um relatório por finding;
  - manifesto com hashes SHA-256.
- Nenhuma escrita ocorre em diretórios de evidência original.
- O adaptador do TCRIA é opcional e não contamina o núcleo.
- README contém arquitetura, contrato de integração e comandos de execução.
