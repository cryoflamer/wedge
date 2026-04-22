# Гайд по скриптам GitHub Codex Pipeline

## Огляд

Цей документ пояснює використання трьох скриптів:

1. export_issues.py — експорт задач з GitHub
2. import_issues.py — створення задач із CSV (+ prompt)
3. comment_issue_prompts.py — додавання prompt’ів до існуючих задач

---

# 1. export_issues.py

Експортує GitHub issues у CSV.

Що робить:
- отримує задачі через gh CLI
- фільтрує за:
    - state (open за замовчуванням)
    - labels
    - діапазоном номерів
- зберігає у CSV

## Використання

```bash
python3 export_issues.py --repo owner/repo
```

## Приклади

Тільки відкриті:

```bash
python3 export_issues.py --repo cryoflamer/wedge
```

Діапазон:

```bash
python3 export_issues.py --repo cryoflamer/wedge --from 10 --to 20
```

Фільтр по labels:

```bash
python3 export_issues.py --repo cryoflamer/wedge --labels ui,interaction
```

Усі задачі:

```bash
python3 export_issues.py --repo cryoflamer/wedge --state all
```

В інший файл:

```bash
python3 export_issues.py --repo cryoflamer/wedge --output issues.csv
```

## Формат CSV

```csv
issue,title,body,labels,state,url
```

---

# 2. import_issues.py

Створює GitHub issues з CSV.

Що робить:
- створює задачі
- додає labels (створює, якщо нема)
- додає assignees/milestone
- додає prompt як comment
- підтримує codex_mode

## Використання

```bash
python3 import_issues.py tasks.csv --repo owner/repo
```

## Приклад CSV

```csv
title,body,labels,codex_mode,agent_prompt
"Fix hover","## Опис...","ui,interaction","fast","Do EXACTLY this..."
```

## Опції

Глобальні labels:

```bash
--labels ui
```

Default codex mode:

```bash
--default-codex-mode fast
```

Dry run:

```bash
--dry-run
```

## Нюанси

- title і body обов’язкові
- agent_prompt опціональний
- prompt додається як comment

---

# 3. comment_issue_prompts.py

Додає prompt’и до існуючих задач.

## Що робить

- додає comment
- додає labels
- додає codex_mode label
- перевіряє існування issue

## Використання

```bash
python3 comment_issue_prompts.py prompts.csv --repo owner/repo
```

## Приклад CSV

```csv
issue,agent_prompt,codex_mode,labels
16,"Do EXACTLY this...","fast","ui"
```

## Опції

Dry run:

```bash
--dry-run
```

Глобальні labels:

```bash
--labels agent
```

Вимкнути codex labels:

```bash
--no-codex-mode-labels
```

## Нюанси

- issue обов’язковий
- agent_prompt обов’язковий

---

# Типові workflow

## A. Є задачі → додаємо prompt

```bash
export → ChatGPT → comment_issue_prompts
```

## B. Нема задач → створюємо

```bash
ChatGPT → import_issues
```

---

# Принципи

- CSV — основний формат
- prompt — тільки в comment
- labels створюються автоматично
- codex_mode дублюється в label
- використовуй dry-run перед запуском

---

# Рекомендація

- export_issues.py — аналіз
- import_issues.py — створення
- comment_issue_prompts.py — ітерації
