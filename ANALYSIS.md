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

`RegistrationView` обрабатывает POST через `RegistrationForm`; форма содержит проверку совпадения паролей и наличия уже зарегистрированного email, а `RegistrationForm.save` пытается создать пользователя через `User.objects.create_user` и получить его через `authenticate` (`RegistrationForm.clean` и `RegistrationForm.save` в `user/forms.py`; `RegistrationView` в `user/views.py`). `AuthView.post` передаёт учетные данные в Django `authenticate` и при успехе вызывает `login`; `LogoutView.get` вызывает `logout` (`user/views.py`). В корневом конфигураторе префикс `user` указан без завершающего `/`, а дочерние пути начинаются с `login/`, `registration/` и `logout/`; при буквальной композиции маршрутов это `/userlogin/`, `/userregistration/` и `/userlogout/` (`config/urls.py`, `user/urls.py`). Имена URL в шаблонах генерируются через `{% url %}` (`user/templates/user/auth.html`, `user/templates/user/registration.html`). HTML-формы отправляют POST с CSRF-токеном (там же).

### Работа с базой данных и фоновые данные

Подключение ORM настроено на PostgreSQL с именем базы `investing`, пользователем `postgres`, адресом `localhost` и портом `5432` (`DATABASES` в `config/settings.py`); Compose публикует PostgreSQL на `5432` и Redis на `6379` (`docker-compose.yml`). Список и детали читают `Share` через ORM; формы и API создают/обновляют/удаляют записи; команда импорта использует `Share.objects.get_or_create` (`dashboard/views.py`, `dashboard/api/v1/views.py`, `dashboard/management/commands/add_shares.py`).

Периодическая задача `update_last_price` получает данные по каждой акции, сравнивает новую цену с сохранённой и обновляет `last_price` и `is_trend_high` через `QuerySet.update`; ошибки внешнего API и обработки отдельной записи логируются (`dashboard/tasks.py`). `get_last_data` возвращает целые единицы цены (`resp.price.units`) и время ответа внешнего API (`dashboard/services/market_data.py`), но задача сохраняет только цену и тренд, не использует возвращённое время (`dashboard/tasks.py`). Поскольку обновление выполняется через `QuerySet.update`, оно не вызывает `save()` экземпляра модели; следовательно, `auto_now=True` у `updated_at` этим обновлением автоматически не срабатывает (`dashboard/models.py`, функция `update_last_price` в `dashboard/tasks.py`).

## 2. Функциональные требования

Ниже описано только поведение, подтверждаемое текущей реализацией. Ограничения и дефекты вынесены после списка и не трактуются как требования.

### Основные возможности и требования

1. **FR-1. Просмотр каталога акций.** Система должна показывать список сохранённых акций с тикером, названием, ISIN, последней ценой и валютой; список сортируется по названию и разбивается на страницы по 100 записей. Для направления изменения цены применяется цветовая индикация. Источник: `ShareListView` в `dashboard/views.py`; шаблон списка в `dashboard/templates/dashboard/list.html`.
2. **FR-2. Просмотр карточки акции.** При выборе акции система должна показывать её название, последнюю сохранённую цену, валюту и время обновления, а также график исторических дневных цен за последние 180 дней. Источник: `ShareDetailView.get` в `dashboard/views.py`; `get_graph` в `dashboard/services/graph.py`; шаблон `dashboard/templates/dashboard/detail.html`.
3. **FR-3. Создание акции через веб-интерфейс.** Авторизованный пользователь должен иметь возможность создать запись акции через форму; после успешного сохранения система перенаправляет его к списку акций. Форма включает все поля модели `Share`. Источник: `ShareCreateView` в `dashboard/views.py`; `ShareModelForm` в `dashboard/forms.py`.
4. **FR-4. Изменение акции через веб-интерфейс.** Авторизованный пользователь должен иметь возможность изменить существующую акцию через форму и после сохранения вернуться к списку. Источник: `ShareUpdateView` в `dashboard/views.py`; `ShareModelForm` в `dashboard/forms.py`.
5. **FR-5. Удаление акции через веб-интерфейс.** Авторизованный пользователь должен иметь возможность запросить удаление акции, подтвердить его формой и после удаления вернуться к списку. Источник: `ShareDeleteView` в `dashboard/views.py`; шаблон подтверждения `dashboard/templates/dashboard/delete.html`.
6. **FR-6. Управление акциями через REST API.** API должно предоставлять операции получения списка и записи, создания, изменения и удаления записей `Share`. В сериализаторе представлены идентификатор, FIGI, ISIN, название, тикер, валюта, последняя цена, признак тренда и время обновления. Источник: `ShareViewSet` в `dashboard/api/v1/views.py`; `ShareSerializer` в `dashboard/api/v1/serializer.py`; регистрация маршрута в `router` в `dashboard/api/v1/router.py`.
7. **FR-7. Фильтрация, поиск и сортировка API-списка.** Клиент API должен иметь возможность фильтровать акции по названию и тикеру, искать по названию и задавать сортировку по названию или тикеру. Источник: `ShareFilter` и `ShareViewSet` в `dashboard/api/v1/views.py`.
8. **FR-8. Пагинация API.** Ответы API со списком должны использовать limit/offset-пагинацию с размером страницы 100 записей. Источник: `REST_FRAMEWORK` в `config/settings.py`.
9. **FR-9. Обработка регистрации.** При отправке формы регистрации система проверяет формат обязательного email, обязательность двух паролей, их совпадение и отсутствие сохранённого пользователя с таким email; обработчик пытается создать пользователя и выполнить вход. Источник: `RegistrationForm` и методы `clean`/`save` в `user/forms.py`; `RegistrationView.post` в `user/views.py`. Успешный результат не гарантирован из-за дефекта, описанного ниже.
10. **FR-10. Вход пользователя.** Посетитель должен иметь возможность войти по email и паролю; при успешной аутентификации создаётся сессия и выполняется переход к списку акций. При неуспешной аутентификации показывается сообщение об ошибке. Источник: `AuthView.post` в `user/views.py`; `AuthForm` в `user/forms.py`.
11. **FR-11. Выход пользователя.** Пользователь должен иметь возможность завершить текущую сессию; после выхода система перенаправляет его к списку акций. Источник: `LogoutView.get` в `user/views.py`.
12. **FR-12. Ограничение веб-операций управления.** Создание, изменение и удаление акции через HTML доступны только пользователям с аутентифицированной сессией; при отказе в доступе view перенаправляет посетителя к списку. Источник: `IsUserAuthenticatedMixin.test_func` и `handle_no_permission`, `ShareCreateView`, `ShareUpdateView`, `ShareDeleteView` в `dashboard/views.py`.
13. **FR-13. Импорт каталога акций.** Команда `add_shares` должна запрашивать у настроенного провайдера список инструментов и создавать отсутствующие записи в базе по данным инструмента; уже существующая запись не создаётся повторно. Источник: `Command.handle` в `dashboard/management/commands/add_shares.py`.
14. **FR-14. Обновление рыночных данных.** Фоновая задача должна для каждой сохранённой акции получать последнюю цену, обновлять её и устанавливать признак тренда в `False`, если новая цена ниже сохранённой, иначе — `True`; при ошибке сравнения признак устанавливается в `True`. Ошибки при получении/обработке данных записываются в журнал. Источник: `update_last_price` в `dashboard/tasks.py`; `get_last_data` в `dashboard/services/market_data.py`.
15. **FR-15. Периодический запуск обновления.** Celery Beat должен запускать задачу `dashboard.tasks.update_last_price` по расписанию с интервалом 10 секунд. Источник: `beat_schedule` в `config/celery.py`.
16. **FR-16. Хранение уникальных идентификаторов акций.** Система должна сохранять у акции FIGI, тикер и UID; FIGI, тикер и UID должны быть уникальны, а тикер ограничен длиной 10 символов. Источник: поля класса `Share` в `dashboard/models.py`.

### Сценарии взаимодействия пользователя

- **Гость просматривает акции:** открывает страницу списка, листает страницы, выбирает тикер для перехода к карточке и графику. Подтверждение: `ShareListView` и `ShareDetailView` в `dashboard/views.py`; шаблоны `dashboard/templates/dashboard/list.html` и `dashboard/templates/dashboard/detail.html`.
- **Авторизованный пользователь управляет каталогом:** открывает форму добавления либо редактирования, сохраняет изменения; для удаления открывает страницу подтверждения. Подтверждение: `ShareCreateView`, `ShareUpdateView`, `ShareDeleteView` в `dashboard/views.py`; шаблоны `dashboard/templates/dashboard/create.html` и `dashboard/templates/dashboard/delete.html`.
- **Посетитель регистрируется или входит:** заполняет email и пароль (при регистрации — дважды), после успешной регистрации/аутентификации перенаправляется к списку; может завершить сессию через выход. Подтверждение: `RegistrationView`, `AuthView`, `LogoutView` в `user/views.py`; формы в `user/forms.py`.
- **API-клиент обслуживает записи акций:** запрашивает список или одну запись и выполняет операции CRUD; при запросе списка использует доступные фильтры, поиск, сортировку и пагинацию. Подтверждение: `ShareViewSet` в `dashboard/api/v1/views.py`; `router` в `dashboard/api/v1/router.py`.
- **Оператор загружает и обновляет данные:** запускает команду импорта, после чего Celery периодически обновляет цены и признак тренда. Подтверждение: `Command.handle` в `dashboard/management/commands/add_shares.py`; `update_last_price` в `dashboard/tasks.py`; `beat_schedule` в `config/celery.py`.

### Неоднозначности, противоречия и возможные дефекты реализации

- **Источник данных и авторизация провайдера.** Код использует Tinkoff Invest API (`get_last_data` в `dashboard/services/market_data.py`, `get_graph` в `dashboard/services/graph.py`, `Command.handle` в `dashboard/management/commands/add_shares.py`), хотя настройка `TINKOFF_TOKEN` в `config/settings.py` содержит пустую строку. В коде не обнаружена интеграция с публичным ISS API Мосбиржи; при отсутствии действующего токена получение рыночных данных не обеспечено.
- **Маршруты аутентификации.** В `config/urls.py` подключение `user.urls` использует префикс `"user"` без завершающего слеша, а дочерние шаблоны путей в `user/urls.py` начинаются с `"login/"`, `"registration/"` и `"logout/"`. Фактические адреса, таким образом, имеют вид `/userlogin/`, `/userregistration/` и `/userlogout/`, а не `/user/login/` и т. п.; reverse по именам в шаблонах использует именно настроенные маршруты. Ожидаемый внешний формат URL неочевиден.
- **Регистрация завершается ошибкой при валидных данных.** `RegistrationForm.clean` в `user/forms.py` вызывает `super().clean()`, но не возвращает `cleaned_data`; при успешной проверке переопределённый метод возвращает `None`. При обработке формы Django присваивает этот результат `self.cleaned_data`, тогда как `RegistrationForm.save` далее индексирует `self.cleaned_data`. В результате попытка создать пользователя завершается ошибкой вместо успешной регистрации. Кроме того, `clean` обращается к значениям по ключам без проверки их наличия, поэтому ошибки проверки обязательных полей также могут вызвать исключение.
- **Проверка формы входа.** `AuthView.post` в `user/views.py` не вызывает `AuthForm.is_valid()` перед чтением значений из `form.data`. Некорректное или неполное тело запроса может привести к ошибке вместо штатного сообщения валидации.
- **Регистрация и нормализация email.** `RegistrationForm.clean` проверяет существование email без приведения к нижнему регистру, тогда как `AuthView.post` переводит email в нижний регистр перед аутентификацией (`user/forms.py`, `user/views.py`). Проверка уникальности и последующий вход используют несовпадающие правила нормализации.
- **Дефект: неаутентифицированный CRUD через REST API.** Для `ShareViewSet` в `dashboard/api/v1/views.py` не указаны permission-классы, а в `REST_FRAMEWORK` в `config/settings.py` не задано глобальное ограничение permissions. В результате анонимный клиент может создавать, изменять и удалять акции через API. Это подтверждают `test_share_create`, `test_share_update` и `test_share_delete` в `DashboardTests` (`dashboard/tests.py`): запросы выполняются без аутентификации и ожидают успешные ответы. Эти тесты закрепляют уязвимое поведение, а не делают его безопасным; отличие от защищённых HTML-операций — дефект контроля доступа.
- **Валидация вычисляемых данных.** `ShareModelForm` в `dashboard/forms.py` включает все поля модели, в том числе `last_price`, `is_trend_high` и `updated_at`; аналогичные поля доступны в `ShareSerializer` в `dashboard/api/v1/serializer.py`. Они могут передаваться при создании/изменении, несмотря на то что также используются как вычисляемые/обновляемые данные.
- **Точность цены и направление тренда.** `get_last_data` в `dashboard/services/market_data.py` берёт только `resp.price.units`, не учитывая дробную часть цены. В `update_last_price` в `dashboard/tasks.py` сравнение с `None` приводит к исключению, которое перехватывается, после чего тренд без сравнения устанавливается в `True`; равная цена также считается ростом.
- **Время обновления.** Задача `update_last_price` в `dashboard/tasks.py` игнорирует возвращаемое `get_last_data` время ответа и выполняет обновление через `QuerySet.update`; поэтому автоматическое поле `updated_at` из `dashboard/models.py` этой задачей не обновляется. Отображаемое время может не соответствовать времени последней котировки.
- **Несовпадение расписания и подписи.** Ключ расписания называется `"add-every-5-min"`, но `schedule` задан равным `10.0` секундам (`config/celery.py`). По реализации можно утверждать только фактический интервал в 10 секунд, а ожидаемое расписание неоднозначно.
- **Доступность карточки при ошибках данных.** `ShareDetailView.get` в `dashboard/views.py` напрямую вызывает `Share.objects.get` и `get_graph`; обработка отсутствующей записи и ошибок внешнего API в этом view не задана. Поведение при таких ошибках не оформлено как отдельный пользовательский сценарий.

## 3. Модернизация

Разделы 1 и 2 фиксируют исходное состояние проекта до модернизации. Ниже приведены выявленные проблемы, принятые решения и результаты проверки уже обновлённой реализации.

### Выявленные проблемы и решения

- **Устаревший стек и риски совместимости.** Исходные требования фиксировали Django 4.1.7, Celery 5.2.7, старые версии DRF/Plotly/Redis и множество транзитивных пакетов напрямую. `requirements.txt` заменён актуальными прямыми зависимостями: Django 5.2 LTS, Celery 5.6, DRF 3.18, django-filter 26.2, Plotly 7.1, psycopg 3.3, Redis 6, Requests и python-dotenv. T-Invest SDK вынесен в отдельный необязательный `requirements-tinvest.txt`, поэтому основной проект не зависит от его установки. Совместимость реально проверена на Python 3.13.14; отдельного Python 3.12 в окружении не было, поэтому запуск именно на 3.12 не выполнялся.
- **Жёсткая зависимость от токена и T-Invest при импорте.** В исходном коде SDK импортировался на верхнем уровне сервисов и команды импорта, а токен задавался в `config/settings.py`. Теперь `get_market_data_provider` в `dashboard/services/market_data.py` выбирает реализацию из `MARKET_DATA_PROVIDER`, по умолчанию `moex`. Классы провайдеров находятся в `dashboard/services/providers/moex.py` и `dashboard/services/providers/t_invest.py`; импорт SDK происходит только внутри методов T-Invest-провайдера. Без токена и даже без установленной T-Invest-библиотеки штатный запуск через ISS не зависит от T-Invest.
- **Провайдер данных и избыточные запросы.** Реализован слой с общим интерфейсом для списка инструментов, пакетных котировок и истории (`MarketDataProvider` в `dashboard/services/market_data.py`). Реализация MOEX использует публичный ISS без авторизации. В `MoexProvider.get_quotes` один ISS-запрос возвращает котировки для всего каталога; Celery запускает обновление раз в 900 секунд (`beat_schedule` в `config/celery.py`). Интервал в 15 минут выбран, чтобы согласовать частоту опроса с заявленной задержкой ISS около 15 минут и не запрашивать данные чаще, чем это имеет смысл для пользователя. Команда `add_shares` загружает каталог и котировки пачками (`Command.handle` в `dashboard/management/commands/add_shares.py`).
- **Проверка формата ISS до реализации.** Формат проверен реальными HTTPS-запросами, а не предположен: ответ списка/котировок содержит секции `securities` и `marketdata`, каждая с массивами `columns` и позиционными строками `data`; дневная история возвращается в секции `candles` с колонками `open`, `close`, `high`, `low`, `value`, `volume`, `begin`, `end`. Это соответствует живым ответам для SBER и GAZP. `MoexProvider._rows` связывает значения с именами колонок и проверяет совпадение длин массивов. Для активной сессии `T` используется `LCURRENTPRICE`, для неактивной сначала `LAST`, затем `LCLOSEPRICE`, `CLOSEPRICE` и `PREVPRICE`. Выбор `LAST` первым уточнён после выборочной проверки реального закрытия AKPP: ISS вернул `LAST=117.76`, `LCLOSEPRICE=117.73`, а close дневной свечи равнялся `117.76`. Регрессионный тест проверяет, что при закрытом рынке выбирается `LAST`, если он доступен.
- **Сопоставление MOEX ISS с `Share`.** ISS не предоставляет FIGI и UID T-Invest, поэтому для MOEX они являются локальными стабильными идентификаторами, а не настоящим FIGI/UID:

  | Поле `Share` | Источник / преобразование |
  |---|---|
  | `figi` | `MOEX:{BOARDID}:{SECID}` |
  | `uid` | Тот же стабильный идентификатор `MOEX:{BOARDID}:{SECID}` |
  | `isin` | `ISIN` из секции `securities` |
  | `ticker` | `SECID` |
  | `name` | `SHORTNAME`, при его отсутствии — `SECNAME` |
  | `currency` | `CURRENCYID` в нижнем регистре; код MOEX `SUR` преобразуется в `RUB` |

  `MoexProvider.list_instruments` пропускает строки без тикера, ISIN или имени, а также тикеры длиннее ограничения модели в 10 символов. Для T-Invest сохраняются его собственные значения FIGI, UID, ISIN, тикера, названия и валюты (`TInvestProvider.list_instruments`). При смене провайдера повторный `add_shares` сопоставляет записи по тикеру и обновляет провайдерские идентификаторы, чтобы перевести общие инструменты на новую систему идентификаторов.
- **Недостаточная точность и время котировок.** `Share.last_price` изменён с `FloatField` на `DecimalField(20, 9)` миграцией `dashboard/migrations/0008_alter_share_last_price.py`. Оба провайдера возвращают `Decimal`; T-Invest преобразует units+nano, MOEX сохраняет точность десятичного значения (`_money` в `TInvestProvider`, `_decimal` в `MoexProvider`). `update_last_price` пакетно обновляет цену, направление изменения и `updated_at` по времени ответа котировки (`dashboard/tasks.py`), а отсутствие предыдущей цены трактуется как начальная запись, а не как ошибка сравнения.
- **Невалидная конфигурация и секреты в коде.** `SECRET_KEY`, `DEBUG`, список хостов, параметры PostgreSQL, брокер Celery, выбранный провайдер, токен T-Invest, его gRPC-адрес и необязательный PEM-путь читаются из окружения; `.env` загружается через python-dotenv (`config/settings.py`). Добавлен `.env.example`, локальный `.env` исключён из Git. `docker-compose.yml` использует переменные для пароля PostgreSQL, именованные тома и healthcheck PostgreSQL/Redis.
- **Дефекты форм и маршрутов пользователя.** Исправлены ошибки обработки неполных форм и регистрации (`AuthView.post`, `RegistrationForm.clean`, `RegistrationForm.save` в `user/views.py` и `user/forms.py`), нормализуется email, URL-префикс изменён на `/user/` (`config/urls.py`). `ShareDetailView.get` использует `get_object_or_404` для отсутствующей акции (`dashboard/views.py`).
- **Анонимное изменение данных через API.** `ShareViewSet` теперь использует `IsAuthenticatedOrReadOnly`: чтение списка и карточки остаётся публичным, POST/PUT/PATCH/DELETE требуют аутентификации (`dashboard/api/v1/views.py`). Тесты CRUD теперь проходят с аутентифицированным пользователем, а отдельные тесты подтверждают HTTP 403 для анонимной записи (`DashboardTests` в `dashboard/tests.py`).
- **Несовместимость новой версии Plotly.** Проверка страницы акции выявила, что Plotly 7 удалил аргумент `show_link`, и карточка возвращала 500. Аргумент удалён из `get_graph` (`dashboard/services/graph.py`), добавлен тест рендеринга графика (`MarketDataProviderTests` в `dashboard/tests_market_data.py`).
- **Запуск на Windows.** Для Windows worker запускается с пулом `solo`; старый совет использовать Eventlet удалён из документации. Команды установки, запуска базы/Redis, миграций, сайта, worker и Beat обновлены в `README.md`.

### Проверки и границы верификации

| Проверка | Результат |
|---|---|
| `python -m pip check` в `.venv` | Пройдена: конфликтов зависимостей не найдено |
| `manage.py check` | Пройдена |
| `manage.py makemigrations --check --dry-run` | Пройдена: незаписанных изменений модели нет |
| Полный `manage.py test` | Пройдены все 23 теста, включая регистрацию, права API, сопоставление ISS, пакетность, точность цены и график |
| Docker Compose | PostgreSQL 17 и Redis 7 запущены и перешли в `healthy`; миграции применены до `dashboard.0008_alter_share_last_price` |
| Реальные запросы MOEX ISS | Проверены список SBER/GAZP, поля котировок и формат дневных свечей; провайдером загружены 402 инструмента и 399 котировок |
| Повторный `manage.py add_shares` и обновление цены | Импорт оставил 402 записи; синхронный вызов задачи обновил 399 цен. Три инструмента без ответа в котировочной секции пропущены с предупреждением |
| HTTP smoke test работающего сайта | `/`, `/api/v1/shares/?limit=1`, `/user/login/` и карточка акции с графиком вернули HTTP 200; API вернул 402 записи |
| Celery на Windows | Worker `-P solo` подключился к Redis, ответил на `inspect ping`; отправленная через брокер задача `update_last_price` обработана worker и завершилась успешно (399 обновлений). Beat запущен с расписанием 900 секунд |
| T-Invest endpoint | DNS и TCP-подключение к `invest-public-api.tbank.ru:443` проверены; базовая конфигурация MOEX запускалась без установленного SDK и без токена |

Фактический запуск выполнен на Python 3.13.14 и Windows 11. T-Invest API-запросы не выполнялись: токена и доступа нет. Поэтому авторизация T-Invest, получение данных через этот API и ветка соединения с пользовательским PEM-сертификатом проверены по реализации/интерфейсу SDK, но не были интеграционно проверены. Разделы 1–2 выше сохранены как анализ исходного состояния, поэтому их упоминания старых дефектов описывают baseline, а не итоговое поведение.

### Дополнительная выборочная проверка по чек-листу

26 октября 2026 года в 21:13–21:16 по Москве сверены ровно первые 15 акций каталога в порядке списка (`ShareListView`, сортировка по `name`): MSNG, XLAMIX, AIIQ, AKAI, AKBC, AKCN, AKFB, AKFN, AKGD, AKGP, AKHT, AKMC, AKMM, AKMP, AKPP. Выполнен один фильтрованный пакетный запрос ISS, который вернул 15 котировок, и получены 15 страниц этих инструментов на официальном сайте MOEX (все HTTP 200). Проверка не распространялась на остальные инструменты каталога.

В таблице сравнивается сохранённая цена приложения на момент проверки с close дневной свечи ISS за 26 октября. Для активных инструментов `TRADINGSTATUS=T` эта свеча ещё обновлялась, поэтому её close в момент запроса не является гарантированной окончательной ценой закрытия; их текущая цена в приложении обновлялась в 20:10–20:26, а выборка ISS/страницы сайта делалась около 21:13.

| Тикер | Цена приложения | Close свечи ISS на 21:16 | Статус ISS |
|---|---:|---:|---|
| MSNG | 1.350 | 1.350 | T |
| XLAMIX | 1124 | 1124 | N |
| AIIQ | 11.501 | 11.501 | N |
| AKAI | 99.92 | 99.85 | T |
| AKBC | 97.20 | 97.20 | T |
| AKCN | 79.30 | 79.40 | T |
| AKFB | 143.09 | 143.09 | T |
| AKFN | 99.50 | 99.50 | T |
| AKGD | 231.99 | 232.08 | T |
| AKGP | 1.131 | 1.131 | T |
| AKHT | 97.63 | 97.04 | T |
| AKMC | 1279.12 | 1277.70 | T |
| AKMM | 180.26 | 180.25 | T |
| AKMP | 1.2832 | 1.2834 | T |
| AKPP | 117.73 | 117.76 | N |

Для неактивных XLAMIX и AIIQ сохранённая цена совпала с close свечи и отображаемым на странице MOEX полем последней сделки. У AKPP обнаружено расхождение: цена в базе устарела и не совпала с последним close; живая свеча и страница MOEX показывали 117.76. Это выявило проблему приоритета полей ISS, исправленную в `MoexProvider.get_quotes`: вне активной сессии `LAST` теперь приоритетнее `LCLOSEPRICE`. Точечный тест провайдера проверяет это поведение. Поле `PREVLEGALCLOSEPRICE` на странице MOEX относится к предыдущей торговой дате (в этой выборке — 23 октября), поэтому оно не использовалось как close за 26 октября.

Добавлены точечные проверки: регистрация с заглавными буквами в email, вход с заглавными буквами, выход из сессии и HTTP 404 для несуществующей HTML-страницы акции. После этих изменений успешно прошли 13 относящихся к ним тестов; ранее полный набор из 23 тестов проходил до добавления этих четырёх тестов и исправления приоритета `LAST`. В базе остаются значения с последнего обновления, видимые в таблице; очередной запуск штатного обновления цен применит исправленное правило к каталогу.
