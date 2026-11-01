# Syno CLI — Консольный менеджер Synology NAS (DSM Web API)

Асинхронная утилита командной строки (CLI) на Python для комплексного мониторинга и управления сетевыми хранилищами **Synology NAS** исключительно через официальный **Synology DSM Web API** (REST/JSON по HTTP/HTTPS без необходимости включения SSH).

---

## 🚀 Основные возможности

* **Мониторинг и состояние системы (`SYNO.Core.*`, `SYNO.Storage.*`):**
  * Сводная панель состояния NAS: модель, версия DSM, аптайм, температура, загрузка CPU и использование RAM.
  * Аудит физических дисков: модель, объём, температура и статус здоровья SMART.
* **Управление Docker / Container Manager (`SYNO.Docker.*`):**
  * Просмотр запущенных и остановленных контейнеров (`syno docker ps`) и локальных образов (`syno docker images`).
  * Скачивание новых образов из Docker Registry (`syno docker pull <image:tag>`).
  * Создание и запуск новых контейнеров с пробросом портов, томов и переменных окружения (`syno docker run`).
  * Старт, остановка и управление проектами Docker Compose.
* **Управление виртуальными машинами (`SYNO.Virtualization.API.*` — VMM):**
  * Таблица виртуальных машин с отображением статуса, vCPU и выделенной памяти (`syno vm list`).
  * Импорт установочных образов ISO, OVA и виртуальных дисков в хранилище VMM (`syno vm image-import`).
  * Создание новых виртуальных машин с монтированием ISO (`syno vm create`).
  * Управление питанием ВМ (`syno vm start`, `syno vm stop`).
* **Управление файлами на томах хранилища (`SYNO.FileStation.*`):**
  * Навигация и просмотр общих папок и вложенных директорий (`syno files ls`).
  * Создание папок (`syno files mkdir`), загрузка файлов на NAS (`syno files upload`) и удаление (`syno files rm`).
* **Мониторинг и управление закачками (`SYNO.DownloadStation.*`):**
  * Отображение суммарной скорости скачивания/отдачи и детальной очереди задач с процентом выполнения (`syno download list`).
  * Добавление новых торрент/magnet/HTTP-закачек (`syno download add`), пауза и возобновление (`syno download pause/resume`).

---

## 📁 Структура проекта

```text
syno_cli/
├── pyproject.toml                   # Конфигурация зависимостей Poetry, скрипта `syno` и pytest
├── README.md                        # Документация проекта
├── .env.example                     # Шаблон переменных окружения
├── .zed/
│   └── debug.json                   # Профили отладки для редактора Zed
├── syno_cli/
│   ├── __init__.py
│   ├── config.py                    # Настройки подключения (Pydantic Settings)
│   ├── exceptions.py                # Иерархия исключений и словарь кодов ошибок DSM
│   ├── client/
│   │   ├── __init__.py
│   │   ├── base.py                  # Базовый HTTP-клиент, авторизация, кэш SID и автоперелогин
│   │   ├── core.py                  # Системный мониторинг и состояние дисков
│   │   ├── docker.py                # Управление контейнерами, образами и Compose-проектами
│   │   ├── vmm.py                   # Управление виртуальными машинами и образами VMM
│   │   ├── file_station.py          # Операции с файлами и папками (File Station)
│   │   └── download_station.py      # Мониторинг и управление задачами Download Station
│   ├── views/
│   │   ├── __init__.py
│   │   ├── formatters.py            # Форматирование байтов, скоростей, аптайма и цветов
│   │   └── tables.py                # Отрисовка таблиц и панелей Rich
│   └── commands/
│       ├── __init__.py
│       └── main.py                  # Иерархия CLI-команд Typer
└── tests/
    ├── __init__.py
    ├── test_auth_and_core.py        # Тесты логина, кэша сессии, автоперелогина и утилит
    └── test_subsystems.py           # Изолированные MockTransport-тесты Docker, VMM, Files и Downloads
```

---

## 🛠 Установка и настройка

### 1. Установка зависимостей через Poetry

```bash
poetry config virtualenvs.in-project true
poetry install
```

### 2. Настройка переменных окружения

Скопируйте шаблон `.env.example` в `.env` и укажите реквизиты вашего Synology NAS:

```bash
cp .env.example .env
```

| Переменная | Описание | По умолчанию |
| :--- | :--- | :--- |
| `SYNO_HOST` | IP-адрес или домен Synology NAS | `192.168.1.100` |
| `SYNO_PORT` | Порт DSM (`5000` — HTTP, `5001` — HTTPS) | `5000` |
| `SYNO_USER` | Имя пользователя DSM | `admin` |
| `SYNO_PASSWORD` | Пароль пользователя | `password` |
| `SYNO_SECURE` | Использовать HTTPS (`true` / `false`) | `false` |
| `SYNO_OTP_CODE` | Одноразовый код 2FA (при необходимости) | — |

---

## 💻 Примеры использования CLI

### Системный статус и диски
```bash
poetry run syno status
poetry run syno storage
```

### Управление Docker (Container Manager)
```bash
# Список контейнеров и локальных образов
poetry run syno docker ps
poetry run syno docker images

# Загрузка нового образа
poetry run syno docker pull redis:alpine

# Создание и запуск нового контейнера
poetry run syno docker run --name my-redis --image redis:alpine -p 6379:6379 -v /docker/redis:/data -e TZ=Europe/Moscow

# Старт / стоп контейнера
poetry run syno docker start my-redis
poetry run syno docker stop my-redis
```

### Управление виртуальными машинами (VMM)
```bash
# Список виртуальных машин
poetry run syno vm list

# Импорт ISO-образа из папки на NAS в VMM
poetry run syno vm image-import --name ubuntu-26.04 --path /isos/ubuntu-26.04-live-server-amd64.iso --type iso

# Создание новой виртуальной машины
poetry run syno vm create --name ubuntu-srv --cpu 4 --memory 4096 --storage "Storage Pool 1" --disk 40 --iso ubuntu-26.04

# Запуск и мягкое выключение ВМ
poetry run syno vm start ubuntu-srv
poetry run syno vm stop ubuntu-srv
```

### Управление файлами на хранилище (File Station)
```bash
poetry run syno files ls /
poetry run syno files ls /docker
poetry run syno files mkdir /docker my_new_folder
poetry run syno files upload ./local_config.yml /docker/my_new_folder
poetry run syno files rm /docker/my_new_folder/local_config.yml
```

### Мониторинг и управление закачками (Download Station)
```bash
# Просмотр общей скорости и списка активных загрузок
poetry run syno download list

# Добавление задачи по ссылке или magnet
poetry run syno download add "https://releases.ubuntu.com/26.04/ubuntu-26.04-live-server-amd64.iso" --dest /downloads

# Пауза и возобновление задачи
poetry run syno download pause dbid_1
poetry run syno download resume dbid_1
```

---

## 🧪 Тестирование

Все тесты используют `httpx.MockTransport` и выполняются полностью автономно без подключения к реальному NAS:

```bash
poetry run pytest -v
```
