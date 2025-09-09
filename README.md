# Что это за проект

Веб-приложение «Расписание колледжа»:

* быстрый **поиск** по группе / преподавателю / предмету (единая строка, подсказки, «чипы»-фильтры);
* выдача **расписания на сегодня / неделю / произвольный период**;
* **экспорт ICS** для календаря;
* **сохранение выбранной группы** в браузере устройства;
* аккуратные **дневные карточки** с парами, статусами («идёт / будет / прошло»), типами занятий, очно/СДО, аудиториями, дом.заданиями;
* «**перерывы**» показываются **только между** парами; день без занятий отображается как **«Выходной»**;
* **«СДО»** подсвечено отдельным цветом и бейджем;
* **тёмная/светлая тема + авто**, бесшовный фирменный фон (варианты для обеих тем), «liquid glass» карточки;
* **адаптивная** мобильная верстка: те же карточки, только компактнее (без «лесенок», скролл бейджей, приятные поля);
* **кабинет преподавателя** (неделя): агрегированная статистика, список занятий, действия «Домашнее задание» и «Сменить кабинет».

Рабочая тайм-зона фронтенда: **Europe/Kaliningrad**.

---

# Готовность по блокам (оценка в %)

* Поиск, подсказки, чипы, фильтры — **95%**
  (всё работает; из приятных доработок — подсветка совпадений и «пустой» экран-инструктаж).
* Периоды (Сегодня/Неделя/Произвольный) — **95%**
  (UI готов; можно добавить сохранение последнего режима).
* Отрисовка дней/пар, нормализация перерывов, «Выходной» — **100%**.
* Бейджи «идёт/будет/прошло» по реальному времени — **100%** (Калининград).
* СДО/очно, тип занятия, аудитория/корпус — **100%**.
* Экспорт ICS — **90%** (работает; можно добавить персональные приватные ICS-ссылки).
* Сохранение группы в префы устройства — **100%**.
* Тёмная/светлая/авто тема — **90%**
  (UI переключатель есть, фоновые паттерны обеих тем есть, можно добавить high-contrast).
* Мобильная версия (компактные «десктопные» карточки) — **95%**.
* Кабинет преподавателя (неделя) — **80%**
  (статистика, список, ДЗ, смена кабинета — уже работают; далее: аудит, подтверждения, история изменений).
* Доступность/ARIA — **70%**
  (читаемые контрасты, фокус-стили — есть; требуется добавить skip-links, роли списков, лайв-объявления).

---

# Использованные технологии

**Фронтенд**

* Чистый **Vanilla JS** (без фреймворков), модульные хелперы.
* **CSS-переменные** (цветовые токены), `color-mix()`, `backdrop-filter` для «стекла».
* **CSS Grid/Flex** адаптивная раскладка, кастомные контролы.
* Подсказки через «**портал**» (абсолютно позиционируем в `body`).
* Авто/ручная **тема** (localStorage + `prefers-color-scheme`).

**Бэкенд (ожидаемый стек)**

* **Django** (шаблоны + API-эндпоинты), Python 3.11+.
* Формат API — **JSON**; экспорт календаря — **ICS**.
* База: любая поддерживаемая Django (SQLite/Postgres/MSSQL — по окружению).
* Статика — через IIS (на проде) или `collectstatic` локально.

---

# Краткая «документация API» (фронт пользуется этим)

**Подсказки**

* `GET /api/suggest/groups/?q=строка` → `[{id, label}]`
* `GET /api/suggest/teachers/?q=строка` → `[{id, label}]`
* `GET /api/suggest/disciplines/?q=строка` → `[{id, label}]`

**Расписание**

* `GET /api/schedule/today/?group=КОД` **или** `?teacher=ID`
* `GET /api/schedule/period/?group=КОД&start=YYYY-MM-DD&end=YYYY-MM-DD`
  (или `teacher=ID`)

Ответ по дням:

```json
[
  {
    "date": "2025-09-08",
    "items": [
      {
        "id": 123,
        "order": 1,
        "time": "08:20–09:50",
        "discipline": "МДК...",
        "lesson_type": "Лекция",
        "teacher": "Иванов И.И.",
        "is_remote": false,
        "remote_platform": null,
        "room": "205",
        "building": "Корпус A",
        "homework": "параграф 3"
      },
      { "break": true, "order": 2, "time": "09:50–10:10" }
    ]
  }
]
```

**Нормализация «перерывов»** (на фронте): перерывы показываются **только если** есть занятие **до** и **после**. День без занятий превращается в `holiday=true`.

**ICS**

* `GET /api/export/ics/?group=КОД&start=...&end=...`
  или `?teacher=ID&start=...&end=...`

**Преференции**

* `GET /api/prefs/get_group/` → `{group:"23ИСПп3-09"}`
* `GET /api/prefs/set_group/?group=...`

**Кабинет преподавателя**

* `GET /api/teacher/me/stats/?start=...&end=...`
  → `{ total_lessons, total_hours, working_days }`
* `GET /api/teacher/me/schedule/?start=...&end=...` → аналогично расписанию
* `POST /api/teacher/homework/set/` — `FormData(lesson_id, text)`
* `GET /api/teacher/room/free/?lesson_id=...` → список свободных комнат
* `POST /api/teacher/room/change/` — `FormData(lesson_id, room_id)`

---

# Как работает фронтенд

* Единая строка поиска вызывает **три эндпоинта подсказок** параллельно; рендер через «портал» (`position: fixed`) — список позиционируется ровно под инпутом, даже если страница прокручена.
* Выбранные элементы превращаются в **чипы** с крестиком. Любой чип можно сбросить.
* Блок «Период» мгновенно перевызывает загрузку данных; в режиме «Период» активируются поля даты.
* **Статус пары** («идёт/будет/прошло») вычисляется на клиенте с учётом тайм-зоны **Europe/Kaliningrad**.
* Адаптация под телефон делает **те же карточки**, только компактнее; края аккуратные, без «edge-to-edge», бейджи прокручиваются горизонтально.

---

# Планы

* Приватные ICS-ленты для пользователей; подписка одним кликом.
* Импорт/сверка расписаний из XLSX/CSV.
* Пуш-уведомления об изменениях по подписке.
* Кэширование (etag/last-modified), CDN для статики.
* Тесты (unit+e2e), CI/CD (GitHub Actions).
* Аудит действий (кто менял кабинет/ДЗ).

---

# Запуск на Windows (локально и прод)

## 0) Предусловия

* **Windows Server 2019/2022** (для прод) или Windows 10/11 (для локали).
* **Python 3.11+**, **Git**, **IIS** (для прод), URL Rewrite + ARR (если идёте через обратный прокси).
* Права администратора.

## 1) Клонирование и окружение

```powershell
git clone <repo-url> college-schedule
cd college-schedule

py -3.11 -m venv venv
venv\Scripts\activate

pip install -U pip wheel
pip install -r requirements.txt   # если нет - поставьте Django, wfastcgi/или waitress
```

Создайте `.env` (или задайте переменные окружения):

```
DJANGO_SETTINGS_MODULE=project.settings
SECRET_KEY=смените-на-секрет
DEBUG=False
ALLOWED_HOSTS=example.com,www.example.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
TIME_ZONE=Europe/Kaliningrad
```

В `settings.py` (важное):

```python
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv("DEBUG","False")=="True"
SECRET_KEY = os.getenv("SECRET_KEY")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS","").split(",")

CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS","").split(",")

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static_root"   # на проде
```

Соберите статику:

```powershell
python manage.py collectstatic --noinput
```

База (если SQLite):

```powershell
python manage.py migrate
python manage.py createsuperuser
```

Проверка локально:

```powershell
python manage.py runserver 0.0.0.0:8000
```

## 2А) Прод через IIS + **wfastcgi** (прямой запуск Django)

1. **Установите IIS** и **URL Rewrite** (через «Turn Windows features on/off» и Web PI).

2. В окружении проекта поставьте:

   ```powershell
   pip install wfastcgi
   python -m wfastcgi-enable
   ```

   Это зарегистрирует FastCGI-обработчик.

3. Создайте каталог деплоя, например:
   `C:\inetpub\college\app` — код, `C:\inetpub\college\static_root` — статика.

4. В IIS ➜ **Sites** ➜ **Add Website…**

   * *Site name*: `college`
   * *Physical path*: `C:\inetpub\college\app`
   * *Binding*: HTTP :80 (временно; HTTPS добавим позже).

5. В корне сайта создайте `web.config`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>

    <handlers>
      <!-- Все запросы в FastCGI (Django) -->
      <add name="Python FastCGI"
           path="*"
           verb="*"
           modules="FastCgiModule"
           scriptProcessor="C:\inetpub\college\venv\Scripts\python.exe|C:\inetpub\college\venv\Lib\site-packages\wfastcgi.py"
           resourceType="Unspecified" />
    </handlers>

    <fastCgi>
      <application fullPath="C:\inetpub\college\venv\Scripts\python.exe"
                   arguments="C:\inetpub\college\venv\Lib\site-packages\wfastcgi.py"
                   stdoutLogEnabled="true"
                   stdoutLogFile="C:\inetpub\logs\wfastcgi-college.log">
        <environmentVariables>
          <add name="DJANGO_SETTINGS_MODULE" value="project.settings" />
          <add name="WSGI_HANDLER" value="project.wsgi.application" />
          <add name="PYTHONPATH" value="C:\inetpub\college\app" />
          <add name="SECRET_KEY" value="замените-на-секрет" />
          <add name="SERVER_PORT_SECURE" value="1" />
        </environmentVariables>
      </application>
    </fastCgi>

    <!-- Статика (отдаёт IIS, минуя django) -->
    <staticContent>
      <remove fileExtension=".svg" />
      <mimeMap fileExtension=".svg" mimeType="image/svg+xml" />
    </staticContent>

    <rewrite>
      <rules>
        <!-- (добавим редирект на https позже) -->
      </rules>
    </rewrite>

  </system.webServer>
</configuration>
```

6. В IIS создайте **Virtual Directory** `/static/` ➜ укажите `C:\inetpub\college\static_root`.
   Запустите сайт — должен открыться.

## 2B) Прод через IIS + **Reverse Proxy (ARR)** + **Waitress** (альтернатива)

Иногда так проще дебажить.

1. Установите **Application Request Routing** и **URL Rewrite**.
2. В проекте:

   ```powershell
   pip install waitress
   ```
3. Запустите как службу (рекомендуется через **NSSM**):

   ```powershell
   waitress-serve --port=8000 project.wsgi:application
   ```
4. В IIS добавьте сайт и включите **Reverse Proxy** на `http://localhost:8000/`.
   Отдачу `/static/` настройте как физический каталог, чтобы не грузить Python.

---

# Привязка домена и HTTPS (IIS)

## 1) DNS

* В панели регистратора домена создайте записи:

  * `A` — на публичный IPv4 вашего сервера;
  * (опционально) `AAAA` — на IPv6.
* Подождите обновления DNS (обычно до часа).

## 2) Привязка домена в IIS

* В IIS ➜ ваш сайт ➜ **Bindings…** ➜ **Add…**:

  * `http` : 80, **Hostname** = `example.com` (и отдельно `www.example.com`, если нужно).
* Проверите, что сайт по HTTP открывается (временно).

## 3) Выпуск бесплатного SSL (Let’s Encrypt) через **win-acme**

1. Скачайте **win-acme** (wacs.exe) с официального сайта.
2. Запустите от администратора:

   ```
   wacs.exe
   ```

   Выберите:

   * `N` — *Create new certificate (simple)*;
   * Выберите нужный сайт IIS (hostname подтянется);
   * Разрешите автоматическую установку привязки 443 и авто-продление.

win-acme создаст сертификат, добавит **binding :443**, настроит планировщик для продления.

## 4) Редирект HTTP → HTTPS и HSTS

В `web.config` добавьте:

```xml
<system.webServer>
  <rewrite>
    <rules>
      <rule name="HTTP to HTTPS" stopProcessing="true">
        <match url="(.*)" />
        <conditions>
          <add input="{HTTPS}" pattern="off" ignoreCase="true" />
        </conditions>
        <action type="Redirect" url="https://{HTTP_HOST}/{R:1}" redirectType="Permanent" />
      </rule>
    </rules>
  </rewrite>

  <httpProtocol>
    <customHeaders>
      <!-- 6 мес HSTS; включайте после проверки, только если всё на https -->
      <add name="Strict-Transport-Security" value="max-age=15552000; includeSubDomains; preload" />
    </customHeaders>
  </httpProtocol>
</system.webServer>
```

---

# Эксплуатация и чек-лист продакшена

* `DEBUG = False`, корректные `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.
* `SECRET_KEY` храните в системных переменных или в секрете IIS.
* `collectstatic` выполнен, `/static/` выдан IIS напрямую.
* Часовой пояс в БД и приложении согласован (на фронте — Европа/Калининград).
* Логи FastCGI/приложения пишутся в читаемое место (`C:\inetpub\logs\...`).
* Бэкапы БД + секретов + `static_root`.
* Автопродление win-acme работает (есть планировщик).
* Если используете SQLite — файл БД должен быть на диске вне каталога деплоя и с бэкапом; на прод лучше Postgres.
* HTTP-заголовки безопасности (HSTS, X-Content-Type-Options, X-Frame-Options) — можно добавить в `web.config`.
* Проверить CORS/CSRF, если API будет вынесен на отдельный поддомен.

---

# Небольшие технические заметки

* **Подсказки** строятся из трёх источников, группируются в выпадашке с «липкими» заголовками разделов (Группы/Преподаватели/Предметы).
* **Разметка карточек** — один шаблон и на десктопе, и на мобиле; CSS-медиа-правила просто поджимают размеры, не ломая геометрию.
* «**Перерыв**» в ответе API может приходить в любом месте — фронт его **фильтрует** и оставляет только те, что действительно **между** двумя парами.
* **СДО** (дистанционно) — в карточке: замена аудитории на текст «Дистанционно» и бейдж (цвет зависит от темы).

---

# Что ещё будет улучшено

* Добавить кеширование запросов расписания на период (ETag/If-None-Match).
* Микро-анимации (hover/focus) с учётом `prefers-reduced-motion`.
* Тултипы по бейджам (title/aria-label).
* Лёгкая пагинация по неделям кнопками «← →» (без открытия календаря).

---

## 2025 PhantomF0rge / MeowLogic