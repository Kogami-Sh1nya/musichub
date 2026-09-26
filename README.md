# MusicHub Backend

FastAPI + PostgreSQL backend for MusicHub.

## 1. Почему `docker compose` у вас сейчас падает

Ошибка вида:

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
```

означает не ошибку Python или FastAPI. В Windows Docker CLI не может подключиться к Linux Engine — обычно Docker Desktop не запущен.

Проверьте:

```powershell
docker version
docker info
```

Если `docker info` не работает с такой же ошибкой, запустите Docker Desktop и дождитесь состояния `Engine running`.

После этого достаточно:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Миграция PostgreSQL теперь запускается автоматически при старте API. Отдельно делать `docker compose exec api alembic upgrade head` не требуется.

## 2. Самое простое тестирование без VK

В `.env` по умолчанию:

```env
VK_MOCK_MODE=true
```

Это специальный dev-режим. Реальный VK client id ему не нужен.

После запуска откройте:

```text
http://localhost:8000/docs
```

Swagger позволяет вручную вызывать REST endpoints.

### Полный сценарий

1. `GET /api/v1/auth/vk/start`.
2. В ответе получите `authorization_url`.
3. Откройте этот URL в браузере.
4. Mock VK автоматически перенаправит браузер обратно в MusicHub и установит HttpOnly cookies.
5. В Swagger выполните `GET /api/v1/me`.
6. Затем проверьте `/library`, `/search`, `POST /library/tracks`, `GET /tracks/{owner_id}/{audio_id}`, `DELETE /library/tracks/{owner_id}/{audio_id}`.
7. `POST /auth/refresh` проверяет ротацию refresh-session.
8. `POST /auth/logout` отзывает refresh-session и очищает cookies.

Файл `docs.http` содержит те же запросы в формате REST Client для VS Code.

## 3. Как это выглядит для frontend

Для cookie-стратегии достаточно:

```js
const response = await fetch("http://localhost:8000/api/v1/library?offset=0&limit=50", {
  credentials: "include",
});

const data = await response.json();
```

Frontend не получает пароль VK и не должен его собирать.

Если выбран header-based вариант, frontend может передавать:

```http
Authorization: Bearer <musicHub-access-token>
```

## 4. Реальный VK

Когда mock-тесты проходят, переключите:

```env
VK_MOCK_MODE=false
VK_CLIENT_ID=<реальный client id>
VK_REDIRECT_URI=http://localhost:8000/api/v1/auth/vk/callback
```

`VK_REDIRECT_URI` должен совпадать с URI, зарегистрированным в VK-приложении.

После переключения запросы `/library`, `/search`, `/tracks` и add/delete проходят через `VkMusicClient` к настроенному VK API.

## 5. Важный предел музыкальной части

Backend не реализует обход рекламы VK, обход DRM, scraping страниц vk.ru, replay browser cookies или изменение защищенного медиапотока. Если разрешенный API конкретного аккаунта/приложения возвращает playable URL, MusicHub может передать этот URL фронтенду.

Для продуктовой функции «без рекламы» нужен официальный способ доступа без рекламы/соответствующая подписка или другой разрешенный механизм, а не технический обход ограничений VK.

## 6. Endpoints

### Auth

- `GET /api/v1/auth/vk/start`
- `GET /api/v1/auth/vk/callback`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`

### User

- `GET /api/v1/me`

### Music

- `GET /api/v1/library?offset=0&limit=100`
- `GET /api/v1/search?q=...&offset=0&limit=50`
- `POST /api/v1/library/tracks`
- `DELETE /api/v1/library/tracks/{owner_id}/{audio_id}`
- `GET /api/v1/tracks/{owner_id}/{audio_id}`

### Health

- `GET /health`

## 7. PostgreSQL

Локальная БД создается Docker Compose:

```text
host: localhost
port: 5432
database: musichub
user: musichub
password: musichub
```

Для самого API внутри compose используется:

```text
postgresql+asyncpg://musichub:musichub@db:5432/musichub
```

## 8. Архитектура

```text
Frontend
   |
   | REST / JSON + HttpOnly cookies
   v
FastAPI
   |
   +-- Auth service ---- VK ID
   |
   +-- Music service --- VK API / mock adapter
   |
   +-- PostgreSQL
```

`VkMusicClient` является адаптером, поэтому бизнес-логику MusicHub можно оставить неизменной при замене транспорта/API.
