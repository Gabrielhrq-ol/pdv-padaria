# CLAUDE.md - PDV Padaria

Sistema de frente de caixa (PDV) local para padaria de bairro. Desenvolvedor: Gabriel. Idioma do projeto: portugues do Brasil (codigo em ingles, textos de tela e cupom em portugues).

## Escopo atual
Cadastro de produtos, frente de caixa com leitor de codigo de barras, estoque, caixa (abertura, sangria, suprimento, fechamento), relatorios e cupom NAO FISCAL impresso em impressora termica ESC/POS.

Fora do escopo (nao implementar sem pedido explicito): NFC-e/nota fiscal, TEF/maquininha, integracao com balanca, delivery, nuvem/sincronizacao.

## Stack
- Python 3.12, FastAPI + Uvicorn
- SQLite (WAL, foreign_keys ON), SQLAlchemy 2, Alembic
- Frontend: HTML + CSS + JavaScript puro servido pelo FastAPI (sem frameworks pesados)
- Impressao: python-escpos (Fase 5+; conferir na documentacao atual os nomes dos conectores)
- Senhas: argon2-cffi (Fase 2+)
- Testes: pytest
- Roda 100% local, sem depender de internet para vender

## Regras inegociaveis
1. Dinheiro SEMPRE em centavos (int). Quantidade SEMPRE em milesimos (int). Nunca float.
2. Todo calculo de total passa por app/money.py (uma unica funcao de arredondamento).
3. Finalizar venda e UMA transacao atomica: venda, itens, pagamentos, baixa de estoque e stock_movements. Se algo falhar, nada e gravado.
4. sale_items copia nome e preco do produto no momento da venda.
5. Produto nunca e apagado, apenas desativado.
6. A venda nunca depende da impressora. Falha de impressao nao desfaz a venda.
7. Servidor escuta somente em 127.0.0.1.
8. Autorizacao checada no backend em toda rota (papeis: admin, caixa).
9. Segredos em .env; .env, data/, *.db e backups/ no .gitignore. Nunca commitar segredo.
10. Consultas via ORM/parametrizadas. Validacao de entrada com Pydantic (extra="forbid").
11. Acoes sensiveis vao para audit_log (cancelamento, desconto, ajuste de estoque, abrir/fechar caixa, login falho).
12. Todo cupom impresso traz "DOCUMENTO SEM VALOR FISCAL" em destaque (texto definido pelo cliente).

## Seguranca (valido para TODAS as fases)

### Rede
- Servidor escuta somente em 127.0.0.1.
- TrustedHostMiddleware aceita apenas 127.0.0.1 e localhost (contra DNS rebinding).
- Nenhum CORS liberado. Proibido `allow_origins=["*"]`.
- /docs, /redoc e /openapi.json ligados APENAS quando ENVIRONMENT=development. Em producao, desligados.

### Validacao
- Pydantic v2 com `extra="forbid"` em todos os schemas (rejeita campos extras).
- Limite de tamanho em todos os campos de texto (ex.: nome ate 120, descricao ate 500).
- Preco, custo, estoque e quantidade NAO negativos.
- Teto maximo em valores (ex.: preco ate 100000000 centavos = R$ 1.000.000,00).
- Unidade restrita a UN, KG, L.
- Codigos (barcode, internal_code) somente ASCII, sem espacos.

### Frontend
- NUNCA usar innerHTML com dado vindo do banco ou do usuario. Usar textContent / createElement.
- Jinja com autoescape ligado em todos os templates.
- Headers de seguranca injetados em TODAS as respostas:
  - Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: no-referrer

### Erros
- Nunca retornar stack trace ao cliente.
- Log interno detalhado em arquivo rotacionado (fase futura: rotacao com RotatingFileHandler).
- Resposta HTTP generica (ex.: {"detail": "Erro interno"}) com status apropriado.

### Segredos
- SECRET_KEY real gerada com o modulo secrets (`secrets.token_urlsafe(32)`), somente no .env.
- .env.example contem apenas placeholder.
- Antes de cada commit, rodar `git diff --cached` e `git ls-files` conferindo que .env e *.db NAO estao no indice.
- config.py falha se SECRET_KEY estiver vazia ou com o valor placeholder.

### Autenticacao (Fase 2+)
- Senhas hasheadas com argon2id (argon2-cffi).
- Sessao por cookie assinado: HttpOnly, Secure, SameSite=Strict, com expiracao.
- CSRF em toda rota mutante (POST, PUT, PATCH, DELETE) quando houver sessao.
- Bloqueio temporario apos 5 tentativas de login erradas em 15 minutos.

### Auditoria e backup
- audit_log para acoes sensiveis (ver regra inegociavel 11).
- Backup com a API nativa do SQLite (nao copiar arquivo com banco aberto).
- Backup em local protegido (fora do Git, segunda copia fora do computador).

### Dependencias
- Versoes fixadas (pin exato) em requirements.txt.
- Rodar `pip-audit` ao final de cada fase e tratar vulnerabilidades conhecidas.

### Relatorio por fase
- Ao final de CADA fase, entregar um relatorio de seguranca por gravidade (critico, alto, medio, baixo) SEM corrigir nada fora do escopo. Correcoes viram Issues/PRs.

## Arquitetura (baixo acoplamento)
- app/routers: recebem e respondem, sem regra de negocio
- app/services: regra de negocio (sales, stock, cash, reports, backup)
- app/services/receipt.py: funcao PURA que monta as linhas do cupom (testavel sem impressora)
- app/services/printer.py: unico modulo que fala com o hardware
- app/models.py, schemas.py, money.py, security.py, db.py, config.py

## Forma de trabalho
- Uma fase por vez, conforme o guia. Comece sempre em modo de plano e me mostre o plano antes de escrever codigo.
- Nao altere nada fora do escopo da fase atual.
- Escreva testes junto com cada regra de negocio (pytest). Cenarios obrigatorios: arredondamento, troco, venda atomica com falha no meio, estoque batendo com movimentos, estorno, fechamento de caixa, permissoes (403), cupom em 32 colunas (ver "Hardware e pendencias").
- Explique funcoes criticas (money.py, sales_service.py) quando eu pedir; eu preciso entender o codigo.
- Auditoria de seguranca: entregue apenas um RELATORIO por gravidade (critico, alto, medio, baixo) e NAO corrija antes de eu ler.
- Issues e Pull Requests para correcoes pos-entrega.
- Hardware real (impressora, leitor) e testado por mim; se algo falhar, vou colar o erro exato e o modelo.

## Hardware e pendencias

### Computador do cliente
- UM UNICO caixa. SEM rede, SEM segundo terminal. NAO implementar multi-caixa.
- Como esse PC e ponto unico de falha, backup em local EXTERNO (pendrive ou pasta sincronizada) e REQUISITO, nao opcional (Fase 9 e 10).
- PC de uso geral (navegador e Office instalados) -> PDV roda ISOLADO em 127.0.0.1.
- Dell Inspiron 620, Intel Core i3-2120 3,30 GHz, 12 GB RAM DDR3, SSD SATA 112 GB (~70 GB usados), Windows 64 bits (versao exata a confirmar).
- Monitor Samsung, resolucao a confirmar. A UI do PDV deve funcionar bem em 1280x720, 1366x768 e 1280x1024, sem depender de tela grande.
- Maquina antiga -> evitar dependencias pesadas e animacoes. Priorizar leveza e resposta rapida.

### Impressora do cliente (nao confirmada)
- Modelo: POS-5890U-L, 58 mm, USB e Bluetooth.
- Compatibilidade com ESC/POS NAO esta confirmada. O teste real esta pendente e sera feito por Gabriel via AnyDesk no computador do cliente.
- Cupom: 32 colunas por padrao (configuravel em settings).
- Corte automatico: desligado por padrao (muitos modelos POS-58xx nao tem guilhotina).
- Acentos: podem exigir ajuste de codepage (CP850 / CP858 / CP860 sao candidatos para pt-BR) ou remocao de acentos com unidecode.
- Ate o resultado do teste: toda impressao usa a implementacao Dummy. NAO implementar impressora real, NAO escolher conector e NAO escolher codepage sem o resultado do teste.
- Quando o resultado chegar (se imprimiu, acentos, corte), ajustar app/services/printer.py conforme o relatado.

### Leitor de codigo de barras
- Modelo: "Barcode Scanner 8200" (modelo generico, tipo pistola).
- Modo teclado (digita codigo + Enter) ainda nao confirmado. Sera testado no Bloco de Notas.

### Balanca
- Cliente NAO tem balanca. Versao 1: operador digita o peso.
- Quando o cliente comprar uma, ele envia o modelo. Integracao fica fora do escopo atual.

### Dados do estabelecimento (CONFIDENCIAIS)
- Dados reais do cliente (nome fantasia, CNPJ, endereco, telefone) NUNCA entram em arquivos versionados (nem em scripts/seed_demo.py nem em migrations nem em testes).
- Mecanismo correto para os dados reais:
  1. `data/cliente.example.json` versionado, apenas com placeholders ficticios.
  2. `data/cliente.json` (ignorado pelo .gitignore, pois `data/` e ignorado) contem os dados reais.
  3. `scripts/seed_cliente.py` le `data/cliente.json` e grava em settings. Nunca commitar.
  4. Antes de cada commit, rodar `git status` e confirmar que `data/cliente.json` NAO aparece.

### Script de teste de impressora
- scripts/test_printer.py existe para o teste real.
- Recebe o nome da impressora como argumento de linha de comando (nunca hardcoded).
- Usa 32 colunas.
- python-escpos NAO esta no requirements.txt da Fase 1. Para rodar o teste, instalar manualmente no computador do cliente:
  ```
  pip install python-escpos==3.1 pywin32
  ```

### Pendencias abertas com o cliente
- Versao exata do Windows.
- Resolucao do monitor.
- Nota fiscal e contador (CRITICA): cliente ainda nao contratou contador. Pode exigir NFC-e no futuro.
- Confirmacao de quem e administrador (ate la, o dono).
- Dia/horario para o teste remoto da impressora e do leitor (via AnyDesk).
- Mensagem de rodape do cupom (provisorio: "Obrigado e volte sempre!").
- Pagamento dividido em mais de uma forma (nao perguntado; o schema de payments ja permite).
- Logotipos: cliente enviou duas versoes. Versao traco simples P/B pode ir no cupom e no cabecalho do sistema. SO depois do teste da impressora (imagem em 58 mm depende de raster ESC/POS). NAO versionar arquivos de logo agora.

## Decisoes do cliente (confirmadas em conversa)

1. **Nota fiscal:** sem NFC-e por enquanto. Cupom traz "DOCUMENTO SEM VALOR FISCAL" em destaque. Pendencia critica aguardando contador.
2. **Operadores:** 2 pessoas (dono + 1). Criar dois usuarios na Fase 2. Troca de turno nao informada.
3. **Desconto e cancelamento:** qualquer operador pode. Implementar como setting (padrao: caixa pode), sempre exigindo motivo e gravando audit_log. Checagem no backend lendo do setting. Relatorio por operador (Fase 8).
4. **Administrador:** ate o cliente confirmar, admin e o dono.
5. **Produtos:** 80 a 150 itens. Priorizar cadastro rapido + importacao CSV (Fase 1 nao faz CSV; adicionar na Fase 1 bis ou Fase 6). Paes e salgados sem codigo de barras -> codigo interno curto + busca por nome. Venda por UN e por peso (peso digitado, sem balanca).
6. **Pagamentos:** dinheiro, debito, credito, PIX, outras (vale, ticket). Formas em TABELA/settings, nao fixas no codigo.
7. **Maquininha:** SP630 Pro, separada e manual. Sem integracao TEF. Sistema so registra valor + forma. Fechamento de caixa mostra total por forma para o operador conferir.
8. **Gaveta de dinheiro:** manual. NAO implementar comando de abertura via impressora. (CONFIRMAR)
9. **Estoque:** todos os produtos. Setting `allow_negative_stock = true` (padrao), pois muitos itens sao de producao propria. NUNCA bloquear venda por estoque zero/negativo; apenas alertar. Entrada manual + ajuste exigem motivo. Toda alteracao passa por stock_movements.
10. **Impressao:** operador escolhe por venda. Atalhos "finalizar e imprimir" / "finalizar sem imprimir". Setting define o padrao. Cupom 32 colunas.
11. **Argox:** cliente respondeu "nao sei". Presumir que NAO ha impressora de etiquetas. Nao implementar nada para ela.
12. **Backup:** pendrive + pasta sincronizada com Google Drive para computador (sem API Google). Script de backup copia para as duas pastas. Lembrar nas Fases 9 e 10.

## Comandos
- Ambiente: python -m venv .venv && .venv\Scripts\activate && pip install -r requirements-dev.txt
- Migracoes: alembic upgrade head
- Rodar: uvicorn app.main:app --host 127.0.0.1 --port 8000
- Testes: pytest
- Auditoria: pip-audit
- Teste de impressora (no cliente): python scripts\test_printer.py "NOME_DA_IMPRESSORA"
