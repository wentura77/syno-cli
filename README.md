# Syno CLI & SDK

Полнофункциональная, масштабируемая CLI-утилита и клиентская библиотека (SDK) на Python 3.11+ для администрирования, аудита и автоматизации сетевых хранилищ **Synology NAS (DSM 7.x+)** исключительно через официальный **DSM Web API** (REST/JSON поверх HTTP/HTTPS, без использования SSH).

Кодовая база построена с соблюдением строгой статической типизации (`mypy --strict`), архитектурного принципа разделения ответственности (SoC), стандартов PEP 257 (Google-style docstrings) и полностью покрыта тестами с мокированием сетевого транспорта (`httpx.MockTransport`).

---

## Основные возможности

- **Аутентификация и безопасность:**
  - Поддержка двухфакторной аутентификации (OTP/2FA).
  - Аппаратное симметричное шифрование сохраненных учетных данных и сессионного токена (`sid`) с привязкой к отпечатку оборудования (`machine-id` / `IOPlatformUUID`).
  - Альтернативное хранение секретов через системный `keyring`.
  - Прозрачный автоперелогин (re-auth) при инвалидации сессии (коды DSM `105`, `106`, `107`, `119`).
  - Безопасное подключение HTTPS по умолчанию (порт `5001`) с корректной обработкой самоподписанных SSL-сертификатов и контролем пула соединений (`Connection: close`, защита от полузакрытых сокетов DSM).

- **Системный мониторинг и журналы:**
  - Сводная панель статуса: модель NAS, версия DSM, аптайм, температура, утилизация CPU и памяти RAM (`syno status`).
  - Диагностика накопителей: емкость, температура, SMART-статусы дисков (`syno storage`).
  - Просмотр системных журналов событий DSM (Log Center) с фильтрацией по критичности и поиском по ключевым словам (`syno logs list`).

- **Container Manager (Docker & Docker Compose):**
  - Управление контейнерами: просмотр статусов (`ps`), запуск (`start`), остановка (`stop`), перезапуск (`restart`) и удаление (`rm`, в т.ч. принудительное `--force`).
  - Развертывание одиночных контейнеров с пробросом портов, томов и переменных окружения (`run`).
  - Мониторинг утилизации ресурсов в реальном времени: CPU, RAM, дисковый ввод-вывод (I/O) и сеть (RX/TX) (`stats`).
  - Потоковое чтение логов контейнеров в естественном хронологическом порядке (`logs`).
  - Управление образами: листинг локальных образов и скачивание из реестров (`images`, `pull`).
  - **Docker Compose:** управление мультиконтейнерными стеками (`compose list`, `compose up`, `compose down`, `compose restart`, `compose logs`).

- **Virtual Machine Manager (VMM):**
  - Просмотр виртуальных машин и зарегистрированных образов ISO/дисков (`vm list`, `vm images`).
  - Импорт установочных ISO/OVA из локальной файловой системы NAS (`vm image-import`).
  - Управление питанием гостевых ОС: запуск, мягкое ACPI-выключение, принудительное отключение и рестарт (`vm start`, `vm stop`, `vm restart`).
  - Создание снимков состояния ВМ (`vm snapshot`).
  - **Расширенное создание виртуальных машин (`vm create`):**
    - Автоматическое обнаружение хостов-гипервизоров, хранилищ (Repo) и виртуальных сетей кластера VMM.
    - Управление поведением и службами: автозапуск при старте NAS (`--autorun`), синхронизация времени (`--sync-time`), профиль ОС (`--windows` / `--linux`), текстовое описание (`--desc`).
    - Сетевые интерфейсы: выбор виртуальной сети (`--network`) и назначение статического MAC-адреса (`--mac`).
    - Тюнинг процессора: прямой проброс инструкций хоста (`--cpu-passthrough`), оптимизации Hyper-V (`--hyperv`), вес планировщика (`--cpu-weight`), привязка к физическим ядрам (`--cpu-pin`).

- **File Station:**
  - Навигация по файловой системе (`ls`) с определением типов файлов, иконками, сортировкой по размеру/дате и автодополнением путей по `Tab`.
  - Создание каталогов (`mkdir`) и удаление файлов/папок (`rm`).
  - Потоковая загрузка (`upload`) и выгрузка (`download`) с отображением интерактивного Rich-прогресс-бара и контролем скорости передачи без переполнения оперативной памяти (поддержка файлов 8+ ГБ).

- **Download Station:**
  - Мониторинг общей скорости загрузки/отдачи и очередей задач (`download list`).
  - Добавление закачек по URL, magnet-ссылкам или локальным `.torrent`-файлам (`download add`).
  - Поддержка путей сохранения с прямыми и обратными слэшами с автоматической нормализацией.
  - Управление жизненным циклом загрузок: приостановка, возобновление и удаление (`download pause`, `download resume`, `download delete`).

---

## Структура проекта

```text
syno_cli/
├── pyproject.toml                  # Конфигурация Poetry, pytest, mypy, ruff, interrogate
├── README.md                       # Документация проекта и справочник команд
├── syno_cli/
│   ├── __init__.py                 # Публичный экспорт SDK (SynoDSM, клиенты, исключения)
│   ├── config.py                   # Конфигурация подключения (Pydantic Settings, platformdirs)
│   ├── constants.py                # Протокольные константы DSM, таймауты, размеры буферов, ExitCode
│   ├── credential_storage.py       # Безопасное хранение логина/пароля (Fernet / Keyring)
│   ├── session_storage.py          # Зашифрованное хранение сессии (sid, api_map) с привязкой к хосту
│   ├── exceptions.py               # Иерархия исключений (DsmApiError, DsmAuthError и др.)
│   ├── facade.py                   # Высокоуровневый асинхронный фасад SDK (SynoDSM)
│   ├── client/
│   │   ├── __init__.py
│   │   ├── base.py                 # Базовый HTTP-клиент (Auth, Info, multipart, stream_download)
│   │   ├── core.py                 # Системный мониторинг, накопители и управление питанием
│   │   ├── docker.py               # Управление контейнерами, образами и проектами Docker Compose
│   │   ├── download_station.py     # Управление задачами закачки в Download Station
│   │   ├── file_station.py         # Файловые операции и потоковая передача в File Station
│   │   ├── logs.py                 # Чтение и фильтрация журналов событий DSM (Log Center)
│   │   └── vmm.py                  # Управление виртуальными машинами, сетями и образами VMM
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── main.py                 # Корневая точка входа Typer CLI
│   │   ├── common.py               # Единый декоратор @cli_command, CommandResult и диспетчер ошибок
│   │   ├── completion.py           # Автодополнение удаленных путей NAS по клавише Tab
│   │   ├── auth_cmd.py             # Команды управления учетными данными (syno auth)
│   │   ├── system_cmd.py           # Команды мониторинга состояния и дисков (status, storage)
│   │   ├── logs_cmd.py             # Команды просмотра системных журналов (syno logs)
│   │   ├── docker_cmd.py           # Команды управления контейнерами и Compose (syno docker)
│   │   ├── vm_cmd.py               # Команды управления виртуализацией (syno vm)
│   │   ├── files_cmd.py            # Команды работы с файлами и папками (syno files)
│   │   └── download_cmd.py         # Команды управления загрузками (syno download)
│   └── views/
│       ├── __init__.py
│       ├── formatters.py           # Форматирование байтов, скоростей, аптайма и статусов
│       └── tables.py               # Генераторы консольных таблиц и панелей Rich
└── tests/
    ├── __init__.py
    ├── test_auth_and_core.py       # Тесты аутентификации, перелогина и системного статуса
    ├── test_security.py            # Тесты шифрования сессии и учетных данных
    └── test_subsystems.py          # Модульные тесты Docker, Compose, VMM, Download Station и Logs

```

---

## Установка и настройка

### Требования

* Python 3.11–3.14
* Менеджер пакетов [Poetry](https://python-poetry.org/)

### Установка зависимостей

```bash
git clone [https://github.com/your-repo/syno_cli.git](https://github.com/your-repo/syno_cli.git)
cd syno_cli
poetry install

```

### Первичная настройка подключения

Вы можете настроить параметры подключения через переменные окружения, файл `.env` или передать учетные данные интерактивно:

```bash
# Скопируйте шаблон окружения
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

Сохраните учетные данные в защищенное хранилище (с аппаратным шифрованием или в системный keyring):

```bash
poetry run syno_cli auth store
# Проверка статуса авторизации и путей к кэшу
poetry run syno_cli auth status

```

---

## Справочник основных CLI-команд

### 1. Мониторинг системы и журналы

```bash
# Общая сводка состояния системы (CPU, RAM, температура, аптайм)
syno_cli status

# Состояние физических накопителей и SMART
syno_cli storage

# Просмотр последних 50 событий системного журнала DSM
syno_cli logs list

# Фильтрация журналов по уровню важности и ключевому слову
syno_cli logs list --level warn --lines 20
syno_cli logs list --level err -q "abnormal"

# Вывод логов в формате JSON
syno_cli logs list --json

```

### 2. Container Manager (Docker)

#### Управление контейнерами и образами

```bash
# Список контейнеров
syno_cli docker ps

# Мониторинг утилизации ресурсов в реальном времени
syno_cli docker stats
syno_cli docker stats my-container

# Чтение последних строк логов контейнера
syno_cli docker logs my-container --lines 50

# Скачивание образа
syno_cli docker pull redis:alpine

# Создание и запуск контейнера
syno_cli docker run -n my-redis -i redis:alpine -p 6379:6379

# Управление состоянием контейнера
syno_cli docker restart my-redis
syno_cli docker stop my-redis
syno_cli docker start my-redis

# Удаление контейнера (включая принудительное удаление работающего)
syno_cli docker rm my-redis --force

```

#### Проекты Docker Compose

```bash
# Список активных проектов Compose
syno_cli docker compose list

# Развертывание/обновление проекта из файла docker-compose.yml
syno_cli docker compose up my-stack ./docker-compose.yml --env-file ./.env

# Остановка сервисов проекта
syno_cli docker compose down my-stack

# Перезапуск проекта
syno_cli docker compose restart my-stack

# Просмотр агрегированных логов проекта
syno_cli docker compose logs my-stack --lines 100

```

### 3. Virtual Machine Manager (VMM)

```bash
# Список виртуальных машин
syno_cli vm list

# Список образов ISO и шаблонов дисков
syno_cli vm images

# Импорт ISO-образа из файловой системы NAS
syno_cli vm image-import ubuntu-24.04 /volume1/iso/ubuntu-24.04-live-server.iso --type iso

# Базовое создание виртуальной машины
syno_cli vm create --name test-vm --cpu 2 --memory 2048 --disk 40

# Создание ВМ с расширенной конфигурацией (сети, процессор, автозапуск)
syno_cli vm create \
  --name prod-srv \
  --cpu 4 \
  --memory 4096 \
  --disk 80 \
  --storage "VM Storage 1" \
  --network "Default Network" \
  --mac "02:11:32:2a:73:ac" \
  --autorun \
  --sync-time \
  --cpu-passthrough \
  --hyperv \
  --desc "Основной сервер приложений" \
  --start

# Управление питанием ВМ
syno_cli vm start prod-srv
syno_cli vm stop prod-srv             # Мягкое ACPI выключение
syno_cli vm stop prod-srv --force     # Принудительное выключение (poweroff)
syno_cli vm restart prod-srv

# Создание моментального снимка состояния
syno_cli vm snapshot prod-srv --desc "Перед обновлением ядра"

```

### 4. File Station

```bash
# Просмотр директории с сортировкой по времени изменения (по умолчанию)
syno_cli files ls /volume1/docker

# Сортировка по размеру файлов
syno_cli files ls /volume1/downloads --sort size

# Создание и удаление каталогов
syno_cli files mkdir /volume1/backup/archive
syno_cli files rm /volume1/backup/old_file.zip

# Потоковая загрузка файла на NAS с прогресс-баром
syno_cli files upload ./large_archive.tar.gz /volume1/backup

# Скачивание файла с NAS
syno_cli files download /volume1/backup/backup.iso --dest ./downloads/

```

### 5. Download Station

```bash
# Мониторинг скорости и список задач
syno_cli download list

# Добавление задачи (URL, magnet-ссылка или торрент) с указанием пути сохранения
syno_cli download add "magnet:?xt=urn:btih:..." --dest "/volume1/downloads/torrents/"
syno_cli download add ./distribution.torrent --dest "downloads/distr"

# Приостановка, возобновление и удаление задач
syno_cli download pause <task_id>
syno_cli download resume <task_id>
syno_cli download delete <task_id>

```

---

## Использование как Python SDK

Клиентская библиотека предоставляет высокоуровневый асинхронный контекстный менеджер `SynoDSM`:

```python
import asyncio
from syno_cli import SynoDSM

async def main() -> None:
    async with SynoDSM() as nas:
        # Системный статус
        status = await nas.core.get_system_info()
        print(f"Подключено к: {status.get('model')} (DSM {status.get('firmware_ver')})")

        # Получение системных журналов с ошибками
        logs = await nas.logs.list_logs(level="err", limit=10)
        print(f"Найдено ошибок в журнале: {len(logs)}")

        # Управление контейнерами Docker
        containers = await nas.docker.list_containers()
        for c in containers:
            print(f"Контейнер: {c.get('name')} | Статус: {c.get('status')}")

        # Виртуальные машины
        vms = await nas.vmm.list_guests()
        for vm in vms:
            print(f"ВМ: {vm.get('guest_name')} | vCPU: {vm.get('vcpu_num')}")

if __name__ == "__main__":
    asyncio.run(main())

```

---

## Разработка и тестирование

Проект поддерживает строгие проверки качества кода:

```bash
# Статический анализ типов (mypy strict)
poetry run mypy syno_cli tests

# Проверка стиля и импортов (ruff)
poetry run ruff check .

# Проверка покрытия докстрингами (interrogate)
poetry run interrogate -v syno_cli

# Запуск полного набора модульных тестов
poetry run pytest -v

```
