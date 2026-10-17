# CLAUDE.md - PDV Padaria

Sistema de frente de caixa (PDV) local para padaria de bairro. Desenvolvedor: Gabriel. Idioma do projeto: portugues do Brasil (codigo em ingles, textos de tela e cupom em portugues).

## Escopo atual
Cadastro de produtos, frente de caixa com leitor de codigo de barras, estoque, caixa (abertura, sangria, suprimento, fechamento), relatorios e cupom NAO FISCAL impresso em impressora termica ESC/POS.

Fora do escopo (nao implementar sem pedido explicito): NFC-e/nota fiscal, TEF/maquininha, integracao com balanca, delivery, nuvem/sincronizacao.

## Stack
- Python 3.12, FastAPI + Uvicorn
- SQLite (WAL, foreign_keys ON), SQLAlchemy 2, Alembic
- Frontend: HTML + CSS + JavaScript puro servido pelo FastAPI (sem frameworks pesados)
- Impressao: python-escpos (conferir na documentacao atual os nomes dos conectores)
- Senhas: argon2-cffi
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
10. Consultas via ORM/parametrizadas. Validacao de entrada com Pydantic.
11. Acoes sensiveis vao para audit_log (cancelamento, desconto, ajuste de estoque, abrir/fechar caixa, login falho).
12. Todo cupom impresso traz "CUPOM NAO FISCAL - SEM VALOR FISCAL".

## Arquitetura (baixo acoplamento)
- app/routers: recebem e respondem, sem regra de negocio
- app/services: regra de negocio (sales, stock, cash, reports, backup)
- app/services/receipt.py: funcao PURA que monta as linhas do cupom (testavel sem impressora)
- app/services/printer.py: unico modulo que fala com o hardware
- app/models.py, schemas.py, money.py, security.py, db.py, config.py

## Forma de trabalho
- Uma fase por vez, conforme o guia. Comece sempre em modo de plano e me mostre o plano antes de escrever codigo.
- Nao altere nada fora do escopo da fase atual.
- Escreva testes junto com cada regra de negocio (pytest). Cenarios obrigatorios: arredondamento, troco, venda atomica com falha no meio, estoque batendo com movimentos, estorno, fechamento de caixa, permissoes (403), cupom em 48 colunas.
- Explique funcoes criticas (money.py, sales_service.py) quando eu pedir; eu preciso entender o codigo.
- Auditoria de seguranca: entregue apenas um RELATORIO por gravidade (critico, alto, medio, baixo) e NAO corrija antes de eu ler.
- Issues e Pull Requests para correcoes pos-entrega.
- Hardware real (impressora, leitor) e testado por mim; se algo falhar, vou colar o erro exato e o modelo.

## Comandos (preencher conforme o projeto evoluir)
- Ambiente: python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
- Migracoes: alembic upgrade head
- Rodar: uvicorn app.main:app --host 127.0.0.1 --port 8000
- Testes: pytest
