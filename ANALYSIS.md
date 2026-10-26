# 1. Анализ кода

## 1. Назначение приложения и технологический стек

**Investing Demo** — серверное веб-приложение для ведения каталога акций: просмотр списка и карточек инструментов, отображение цены и графика исторических цен, а также создание, изменение и удаление записей. Пользовательский интерфейс реализован шаблонами Django; операции с акциями также доступны через REST API. Это следует из `ShareListView`, `ShareDetailView`, `ShareCreateView`, `ShareUpdateView` и `ShareDeleteView` в `dashboard/views.py`, шаблонов `dashboard/templates/dashboard/` и `ShareViewSet` в `dashboard/api/v1/views.py`.

Технологический стек:

- Python и Django 4.1.7 — веб-приложение, маршрутизация, шаблоны, ORM, формы и встроенная аутентификация (`requirements.txt`; настройки в `config/settings.py`; точка входа управления в `manage.py`).
- Django REST Framework и `django-filter` — REST API, сериализация, фильтрация и пагинация (`requirements.txt`; `ShareViewSet` в `dashboard/api/v1/views.py`; `ShareSerializer` в `dashboard/api/v1/serializer.py`).
- PostgreSQL — настроенная основная база данных (`DATABASES` в `config/settings.py`); `docker-compose.yml` описывает контейнеры PostgreSQL и Redis.
- Celery и Redis — фоновое обновление котировок и планировщик задач (`config/celery.py`, функция `update_last_price` в `dashboard/tasks.py`, `CELERY_BROKER_URL` в `config/settings.py`).
- Plotly — построение графика исторических цен (`get_graph` в `dashboard/services/graph.py`).
- Bootstrap 3 через `django-crispy-forms` и локальные CSS-файлы — оформление форм и страниц (`requirements.txt`, `CRISPY_TEMPLATE_PACK` в `config/settings.py`, шаблоны приложений и `*/static/*/css/`).

**Фактически реализованный источник рыночных данных — Tinkoff Invest API, а не публичный ISS API Мосбиржи.** Клиент `tinkoff.invest.Client` используется при получении последней цены, построении графика и загрузке справочника акций (`get_last_data` в `dashboard/services/market_data.py`, `get_graph` в `dashboard/services/graph.py`, `Command.handle` в `dashboard/management/commands/add_shares.py`). Токен берётся из `TINKOFF_TOKEN` в `config/settings.py`; в исходной конфигурации его значение пустое. Зависимости `tinkoff` и `tinkoff-investments` объявлены в `requirements.txt`. Интеграции с ISS Мосбиржи в просмотренном коде нет.

## 2. Структура проекта и основные компоненты

- `manage.py` — CLI-точка входа Django: устанавливает `DJANGO_SETTINGS_MODULE` и передаёт аргументы команде управления Django (`main`).
- `config/` — конфигурация проекта:
  - `settings.py` задаёт приложения, middleware, шаблоны, PostgreSQL, REST Framework, журналирование, параметры Celery и токен внешнего API.
  - `urls.py` подключает административный интерфейс, страницы `dashboard` и маршруты `user`.
  - `celery.py` создаёт Celery-приложение, обнаруживает задачи Django и объявляет расписание.
  - `wsgi.py` и `asgi.py` предоставляют стандартные точки входа WSGI и ASGI.
- `dashboard/` — каталог акций и основные бизнес-сценарии:
  - `models.py` — модель `Share`.
  - `views.py`, `urls.py`, `forms.py` — HTML-страницы и формы CRUD.
  - `services/market_data.py` — получение котировки у внешнего провайдера; `services/graph.py` — получение свечей и формирование Plotly-графика.
  - `tasks.py` — фоновое обновление цены и направления изменения цены.
  - `api/` — DRF-маршрутизация, `ShareViewSet`, фильтрация и `ShareSerializer`.
  - `management/commands/add_shares.py` — команда импорта справочника акций.
  - `admin.py` — конфигурация модели `Share` в Django Admin.
  - `migrations/` — история создания и изменения таблицы акций.
  - `templates/` и `static/` — HTML-шаблоны и CSS пользовательского интерфейса.
  - `tests.py` — API-тесты создания, чтения, изменения и удаления акций, а также проверка HTML-списка (`DashboardTests`).
- `user/` — регистрация, вход и выход:
  - `models.py` использует стандартную Django-модель пользователя через `get_user_model()`, собственной модели пользователя нет.
  - `forms.py` содержит `RegistrationForm` и `AuthForm`.
  - `views.py` содержит `AuthView`, `RegistrationView`, `LogoutView`.
  - `urls.py`, `templates/user/` задают маршруты и страницы аутентификации.
- `requirements.txt` фиксирует Python-зависимости; `docker-compose.yml` описывает инфраструктурные контейнеры PostgreSQL и Redis. Инструкции запуска и краткое описание API приведены в `README.md`.

## 3. Архитектура и взаимодействие компонентов

Приложение построено как Django-проект с двумя приложениями. Входящие HTTP-запросы направляются корневым URL-конфигуратором `urlpatterns` в `config/urls.py`: административные запросы идут в Django Admin, корневой путь — в `dashboard.urls`, путь `user` — в `user.urls`. Маршруты `dashboard.urls.urlpatterns` направляют запросы страниц к class-based views, а вложенный маршрут `api/` подключает API (`config/urls.py`, `urlpatterns` в `dashboard/urls.py`, `urlpatterns` в `user/urls.py`).

Для HTML-сценариев view использует Django ORM и шаблоны. `ShareListView` формирует список акций, сортируемый по имени и разбитый на страницы по 100 записей; `ShareDetailView.get` загружает запись по `id` и передаёт в шаблон данные акции и результат `get_graph`; классы создания, изменения и удаления используют `ShareModelForm` и модель `Share` (`dashboard/views.py`, `ShareModelForm` в `dashboard/forms.py`). Шаблоны `dashboard/list.html` и `dashboard/detail.html` отображают список, цену, направление тренда, время обновления и график.

REST-путь проходит через `dashboard/urls.py` → `dashboard/api/urls.py` → `dashboard/api/v1/urls.py` → `router` в `dashboard/api/v1/router.py`. `DefaultRouter` регистрирует `ShareViewSet` под `shares`; `ModelViewSet` предоставляет стандартные операции чтения и CRUD по queryset модели `Share`. `ShareSerializer` задаёт поля ответа и записи. Класс `ShareViewSet` также включает фильтрацию по имени и тикеру, поиск по имени и сортировку по имени или тикеру (`dashboard/api/v1/views.py`, `dashboard/api/v1/serializer.py`).

Периодическое обновление устроено отдельно от обработки HTTP-запросов: Celery Beat конфигурируется в `config/celery.py`, задача `update_last_price` перебирает `Share`, вызывает `get_last_data` и сохраняет котировку и признак тренда через ORM (`dashboard/tasks.py`). `get_last_data` и `get_graph` обращаются к внешнему Tinkoff API (`dashboard/services/market_data.py`, `dashboard/services/graph.py`). Команда `add_shares` также запрашивает справочник у этого API и сохраняет записи через `get_or_create` (`Command.handle` в `dashboard/management/commands/add_shares.py`).

В расписании `config/celery.py` задача с ключом `add-every-5-min` фактически настроена с интервалом `10.0` секунд, а не пять минут. Это описание существующей конфигурации, а не предполагаемое поведение.

## 4. Библиотеки и внешние зависимости

Основные прямые зависимости из `requirements.txt` и их назначение:

- `Django==4.1.7` — веб-фреймворк, ORM, HTML-формы, сессии и встроенная аутентификация (`config/settings.py`; views в `dashboard/` и `user/`).
- `djangorestframework==3.14.0` — REST API, viewsets и сериализаторы (`dashboard/api/v1/views.py`, `dashboard/api/v1/serializer.py`).
- `django-filter==22.1` — фильтрация API (`ShareFilter` в `dashboard/api/v1/views.py`; настройка backend в `config/settings.py`).
- `celery==5.2.7` и `redis==4.5.1` — задачи, расписание и брокер (`config/celery.py`, `dashboard/tasks.py`, `config/settings.py`).
- `psycopg2-binary==2.9.5` — драйвер PostgreSQL, выбранный в `DATABASES` (`config/settings.py`).
- `tinkoff-investments==0.2.0b50` и `tinkoff==0.1.1` — интеграция с Tinkoff Invest API (`dashboard/services/market_data.py`, `dashboard/services/graph.py`, `dashboard/management/commands/add_shares.py`).
- `plotly==5.13.1` — график истории котировок (`get_graph` в `dashboard/services/graph.py`).
- `django-crispy-forms==2.0` и `crispy-bootstrap3==2022.1` — оформление форм (`config/settings.py`, `dashboard/templates/dashboard/create.html`).

В файле также перечислены сопутствующие/транзитивные библиотеки, в частности `amqp`, `kombu`, `billiard`, `asgiref`, `grpcio`, `protobuf`, `pydantic`, `python-dateutil`, `pytz` и `sqlparse` (`requirements.txt`). Инструменты форматирования и сортировки импортов — `black` и `isort` (там же). Контейнеры PostgreSQL и Redis описаны в `docker-compose.yml`; само Django-приложение в этом Compose-файле отдельным сервисом не запускается.

## 5. Модель данных: сущности, атрибуты и связи

### `Share`

Единственная прикладная модель объявлена классом `Share` в `dashboard/models.py`:

| Атрибут | Тип / ограничения | Назначение |
|---|---|---|
| `id` | Автоматический первичный ключ Django (`BigAutoField` по умолчанию) | Идентификатор записи |
| `figi` | `CharField(max_length=255)`, уникальный | Идентификатор инструмента у используемого провайдера |
| `isin` | `CharField(max_length=255)` | Международный идентификатор ценной бумаги |
| `name` | `CharField(max_length=255)` | Название компании |
| `ticker` | `CharField(max_length=10)`, уникальный | Биржевой тикер |
| `currency` | `CharField(max_length=20)` | Валюта цены |
| `uid` | `CharField(max_length=255)`, уникальный | UID инструмента у используемого провайдера |
| `last_price` | Nullable/blank `FloatField` | Последняя сохранённая цена |
| `is_trend_high` | Nullable/blank `BooleanField` | Признак роста цены |
| `updated_at` | Nullable `DateTimeField(auto_now=True)` | Метка времени автоматического обновления при сохранении модели |

Ограничения, поля и отображаемые имена заданы в классе `Share`; эволюцию схемы отражают миграции `dashboard/migrations/0001_add_share.py`–`0007_add_updated_at.py`.

Пользовательская сущность — стандартная модель Django, возвращаемая `get_user_model()` в `user/models.py`; приложение не объявляет для неё дополнительных полей или отношений. В модели `Share` нет внешнего ключа или иной связи с пользователем, поэтому акции не привязаны к владельцу. Встроенные таблицы Django для пользователей и сессий включены стандартными приложениями в `INSTALLED_APPS` (`config/settings.py`).

## 6. Обработка пользовательских запросов и взаимодействие с БД

### HTML-интерфейс акций

1. `ShareListView` читает объекты `Share` через queryset Django, сортирует по `name` и отображает не более 100 записей на странице. В `dashboard/templates/dashboard/list.html` пользователь видит тикер, название, ISIN, цену и цветовой признак тренда; авторизованному пользователю показываются ссылки управления (`dashboard/views.py`, `dashboard/templates/dashboard/list.html`).
2. `ShareDetailView.get` получает акцию по `id` через `Share.objects.get`, вызывает `get_graph` и рендерит `dashboard/detail.html`. График строится по дневным свечам за последние 180 дней через внешний API (`dashboard/views.py`; `get_graph` в `dashboard/services/graph.py`; `dashboard/templates/dashboard/detail.html`).
3. `ShareCreateView` и `ShareUpdateView` используют `ShareModelForm`; форма включает все поля модели (`dashboard/views.py`, `ShareModelForm` в `dashboard/forms.py`). `ShareDeleteView` удаляет запись стандартным Django generic view. Эти три операции для HTML ограничены `IsUserAuthenticatedMixin`, проверяющим `request.user.is_authenticated`; при отказе он перенаправляет на страницу списка (`dashboard/views.py`).
4. `ShareModelForm` выставляет `fields = "__all__"`, то есть при HTML-создании/редактировании форма включает также поля провайдерских идентификаторов и вычисляемых котировочных данных (`dashboard/forms.py`).

### REST API

Маршрутизатор предоставляет набор операций для `/api/v1/shares/` и отдельных записей: список, чтение одной записи, создание, изменение и удаление. Это стандартное поведение `ModelViewSet` с `Share.objects.all()` и регистрации `shares` в `DefaultRouter` (`dashboard/api/v1/views.py`, `dashboard/api/v1/router.py`; префиксы маршрутов — `dashboard/urls.py`, `dashboard/api/urls.py`, `dashboard/api/v1/urls.py`). Сериализатор принимает/возвращает явно перечисленные поля, включая котировку и время обновления (`ShareSerializer` в `dashboard/api/v1/serializer.py`). Для списка включены пагинация с размером страницы 100 и backend фильтрации (`REST_FRAMEWORK` в `config/settings.py`); `ShareViewSet` задаёт фильтры `name`/`ticker`, сортировку по `name`/`ticker` и поиск по `name` (`dashboard/api/v1/views.py`). В API-viewset отдельная проверка авторизации не задана; глобальная настройка permission-классов также отсутствует в `REST_FRAMEWORK` (`dashboard/api/v1/views.py`, `config/settings.py`).

### Пользователи и аутентификация

`RegistrationView` обрабатывает POST через `RegistrationForm`; форма проверяет совпадение паролей и отсутствие уже зарегистрированного email, создаёт пользователя через `User.objects.create_user`, затем `RegistrationView.post` выполняет вход (`RegistrationForm.clean` и `RegistrationForm.save` в `user/forms.py`; `RegistrationView` в `user/views.py`). `AuthView.post` передаёт учетные данные в Django `authenticate` и при успехе вызывает `login`; `LogoutView.get` вызывает `logout` (`user/views.py`). В корневом конфигураторе префикс `user` указан без завершающего `/`, а дочерние пути начинаются с `login/`, `registration/` и `logout/`; при буквальной композиции маршрутов это `/userlogin/`, `/userregistration/` и `/userlogout/` (`config/urls.py`, `user/urls.py`). Имена URL в шаблонах генерируются через `{% url %}` (`user/templates/user/auth.html`, `user/templates/user/registration.html`). HTML-формы отправляют POST с CSRF-токеном (там же).

### Работа с базой данных и фоновые данные

Подключение ORM настроено на PostgreSQL с именем базы `investing`, пользователем `postgres`, адресом `localhost` и портом `5432` (`DATABASES` в `config/settings.py`); Compose публикует PostgreSQL на `5432` и Redis на `6379` (`docker-compose.yml`). Список и детали читают `Share` через ORM; формы и API создают/обновляют/удаляют записи; команда импорта использует `Share.objects.get_or_create` (`dashboard/views.py`, `dashboard/api/v1/views.py`, `dashboard/management/commands/add_shares.py`).

Периодическая задача `update_last_price` получает данные по каждой акции, сравнивает новую цену с сохранённой и обновляет `last_price` и `is_trend_high` через `QuerySet.update`; ошибки внешнего API и обработки отдельной записи логируются (`dashboard/tasks.py`). `get_last_data` возвращает целые единицы цены (`resp.price.units`) и время ответа внешнего API (`dashboard/services/market_data.py`), но задача сохраняет только цену и тренд, не использует возвращённое время (`dashboard/tasks.py`). Поскольку обновление выполняется через `QuerySet.update`, оно не вызывает `save()` экземпляра модели; следовательно, `auto_now=True` у `updated_at` этим обновлением автоматически не срабатывает (`dashboard/models.py`, функция `update_last_price` в `dashboard/tasks.py`).
