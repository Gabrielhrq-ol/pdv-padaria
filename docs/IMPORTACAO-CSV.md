# Importação de produtos em massa (CSV)

Para cadastrar vários produtos de uma vez (80, 100, 150 itens), você
preenche uma planilha e roda um script. Em vez de digitar um por um
pela tela.

## 1. Preparar a planilha

Baixe o modelo em `data/produtos.example.csv` e abra no **Excel**,
**Google Sheets** ou **LibreOffice Calc**.

### Colunas aceitas

| Coluna | Obrigatória? | O que colocar |
|---|---|---|
| `name` | **sim** | Nome que aparece no cupom (até 120 caracteres). Ex.: `Pao frances` |
| `unit` | **sim** | `UN`, `KG` ou `L` |
| `price` | **sim** | Preço em reais: `18,00`, `R$ 18,00`, `1.234,56`. Também aceita centavos puros (`1800` = R$ 18,00) |
| `barcode` | opcional | Código de barras EAN (só dígitos). Deixe vazio para pão, salgado etc. |
| `internal_code` | opcional | Código interno curto (letras+números, até 10). Ex.: `101`, `A12` |
| `category` | opcional | Nome da categoria. **Cria se não existir** (ex.: `Paes`, `Bebidas`) |
| `stock` | opcional | Estoque inicial. UN como inteiro, KG/L como `0,350`. Default: 0 |
| `min_stock` | opcional | Estoque mínimo (para alerta). Default: 0 |
| `favorite` | opcional | `true` / `false` / `sim` / `nao` / `1` / `0`. Default: `false` |

### Exemplo mínimo

```csv
name,unit,price
Pao frances,KG,"18,00"
Pao de queijo,UN,"3,50"
Refrigerante 2L,UN,"12,00"
```

### Exemplo completo

```csv
name,barcode,internal_code,category,unit,price,stock,min_stock,favorite
Pao frances,,101,Paes,KG,"18,00",10,"1,000",true
Refrigerante 2L,7891111111117,,Bebidas,UN,"R$ 12,00",24,5,false
Leite integral 1L,7891111111148,,Mercearia,L,"6,50","15,000","2,000",false
```

## 2. Salvar como CSV

**Excel / LibreOffice:**
- Arquivo → Salvar como → tipo `CSV (separado por vírgulas)` ou
  `CSV UTF-8 (separado por vírgulas)`.
- Separador pode ser vírgula (`,`) ou ponto-e-vírgula (`;`). O script
  detecta sozinho.

**Google Sheets:**
- Arquivo → Fazer download → Valores separados por vírgulas (.csv).

## 3. Rodar a importação

Abra o PowerShell na pasta do projeto e **ative o ambiente virtual**:

```powershell
cd C:\caminho\para\pdv-padaria
.\.venv\Scripts\activate
```

### Validar sem gravar (recomendado antes do primeiro import)

```powershell
python scripts\import_products.py produtos.csv --dry-run
```

Mostra o que seria importado, aponta erros por linha, e **não grava
nada**.

### Importar de verdade

```powershell
python scripts\import_products.py produtos.csv
```

Resultado típico:
```
inseridos=123 | pulados_existentes=5 | erros=2
```

Erros aparecem com o número da linha, exemplo:
```
Erros encontrados:
  linha 45: price invalido ('abc'): parte inteira invalida: 'abc'
  linha 78: barcode: String should match pattern '^\d+$'
```

### Modo estrito (tudo ou nada)

```powershell
python scripts\import_products.py produtos.csv --strict
```

Qualquer erro ou produto duplicado **aborta e faz rollback**. Útil
quando você quer garantir que ou importa tudo, ou não importa nada.

## 4. Comportamento esperado

- **Idempotente**: se você rodar o mesmo arquivo duas vezes, a segunda
  vez pula tudo (sem duplicar). A chave de duplicação é `barcode` OU
  `internal_code`.
- **Categoria nova**: se `category` tem um nome que não existe, o script
  cria a categoria automaticamente.
- **Produto novo é sempre `active=true`**. Desativação é pela tela.
- **Nenhum produto existente é alterado**. Só INSERT, nunca UPDATE.
- **Limites**: até 2 MB e 2000 linhas por arquivo. Se tiver mais, divida
  em arquivos.

## 5. Erros comuns

| Mensagem | O que fazer |
|---|---|
| `arquivo nao esta em UTF-8` | Salve de novo como `CSV UTF-8` |
| `faltam colunas obrigatorias` | Verifique o cabeçalho (primeira linha) |
| `price invalido` | Use `18,00`, `R$ 18,00` ou `1800` (centavos) |
| `favorite invalido` | Use `true`/`false`/`sim`/`nao`/`1`/`0` |
| `barcode: String should match pattern` | Barcode só aceita dígitos. Deixe vazio se não tem |
| `produto ja existe (id=X)` (strict) | Em modo normal isso é só um "pulado"; só vira erro no `--strict` |

## 6. Recomendação de workflow

1. Peça ao cliente a planilha dos produtos (ele preenche no Excel).
2. Salve em `C:\caminho\para\pdv-padaria\produtos.csv`.
3. Rode `--dry-run` e revise o resumo com o cliente.
4. Se tiver erros: corrige na planilha, salva, roda `--dry-run` de novo.
5. Quando estiver limpo: roda sem flag pra importar de verdade.
6. Confira na tela `/products` que apareceu tudo.

## 7. Backup antes de importar (recomendado em produção)

```powershell
copy data\pdv.db data\pdv.db.backup-antes-do-import
```

Se algo der errado, pode restaurar o backup copiando de volta.
