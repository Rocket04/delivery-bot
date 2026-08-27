# RESEARCH — дип-ресерч плана DeliveryBot (2026-08-28)

> Дип-ресерч по заданию владельца: сверить критерии и допущения `docs/PLAN.md`
> с актуальными данными интернета (канал «эксперименты»). Живой план НЕ менялся —
> рекомендации ниже требуют «ок» владельца.

## Резюме

**Все ключевые допущения плана подтверждаются.** Ни одно «не-цели MVP» не требует
пересмотра; фаза 2 уточняется тремя фактами (Kaspi Merchant API существует и подключается
за 1–3 дня; у Mini App — готовые шаблоны aiogram+FastAPI+React; Яндекс Доставка API доступна
в КЗ с договором для ИП, но окупается только при потоке). Критерии → вердикты в таблице ниже.

## Критерии и допущения → вердикты

| # | Критерий / допущение плана | Вердикт | Обоснование (источники) |
|---|---------------------------|---------|--------------------------|
| 1 | **Kaspi-предоплата вручную (чек → оператор) — верно для MVP** | ✅ подтверждено | P2P-API у Kaspi нет; официальная схема для ИП — Kaspi Pay: QR, «ссылка для оплаты», счёт (бесплатно, комиссия 0,95%, абонплата 1 950 ₸/мес со 2-го месяца) ([business.kaspi.kz/pay](https://business.kaspi.kz/pay/), [guide q1381](https://guide.kaspi.kz/partner/ru/app/connection/q1381), [q1445](https://guide.kaspi.kz/partner/ru/app/conditions/q1445)). Проверка чека оператором — действующий стандарт малого бизнеса КЗ. |
| 2 | **Kaspi Pay по API — фаза 2** (не-цель MVP) | ✅ верно с уточнением | **Merchant API `pay.kaspi.kz/api/v2` существует**: заявка по ИИН/БИН на [kaspi.kz/webpay/partnership](https://kaspi.kz/webpay/partnership), TradePointId + ключ, HMAC-SHA256, регистрация ~1–3 раб. дня. До объёмов держим чеки вручную; автоматизацию — в фазу 2 после подключения Kaspi Pay для ИП ([kaspi.kz/webpay](https://kaspi.kz/webpay/partnership), [aunimeda.com](https://aunimeda.com/blog/kaspi-pay-api-integration-guide)). |
| 3 | **Telegram Payments для еды в КЗ** (проверить наличие провайдера) | ✅ уточнено | KZT поддерживается; реальные провайдеры: PayBox (2,5–4%), CloudPayments KZ, Freedom Pay, Wooppay и др. **Kaspi провайдером Telegram Payments НЕ является** — внутри бота Kaspi цепляется отдельными схемами (ссылка/QR/счёт). Стартегически: включать провайдеров только ради карт/нерезидентов; для местной аудитории Kaspi покрывает 80–90% ([core.telegram.org/bots/payments](https://core.telegram.org/bots/payments), [paybox.kz](https://paybox.kz/), [a-lux.kz](https://a-lux.kz/blog/priem-oplaty-v-telegram-kaspi-karty-stars/)). |
| 4 | **Mini App — фаза 2, не MVP** | ✅ подтверждено | Mini App = обычное веб-приложение: HTTPS, initData-валидация (HMAC-SHA256 от бот-токена + проверка auth_date), открытие кнопкой `web_app`/меню-кнопкой. Для еды Stars неприменимы (только цифровые товары). Стек aiogram+FastAPI+React/Vite — мейнстрим, есть готовые шаблоны ([MrConsoleka/aiogram-miniapp-template](https://github.com/MrConsoleka/aiogram-miniapp-template), [LEADROI/aiogram-miniapp](https://github.com/LEADROI/aiogram-miniapp), [OLOT SOMSA](https://github.com/khajiev13/restaurant-mini-app)). |
| 5 | **Яндекс.Доставка вручную — верно для MVP** | ✅ подтверждено | API Яндекса в КЗ доступен (договор с ИП, OAuth, claims API, вебхуки) — интеграция на дни, НО комиссии/накладные окупаются только при 5–10+ заказах в день; для 1 курьера ручная схема оптимальна. В фазе 2 — кнопка «вызвать курьера Яндекса» под пики ([delivery.yandex.kz/ru](https://delivery.yandex.kz/ru/), [dev.go.yandex/services/delivery](https://dev.go.yandex/services/delivery)). |
| 6 | **ИИ-помощник (эскалация/админка) — фаза 2+** | ✅ подтверждено, дёшево | DeepSeek API платится из КЗ картой напрямую; при нашем трафике ~$2–5/мес. Гибрид «кнопки на оформлении + LLM на свободных вопросах» — отработанный паттерн; главный риск — prompt injection (OWASP LLM Top 10), обязателен человек в контуре ([api-docs.deepseek.com](https://api-docs.deepseek.com/news/news250929), [venturebeat](https://venturebeat.com/technology/deepseeks-new-v3-2-exp-model-cuts-api-pricing-in-half-to-less-than-3-cents)). |
| 7 | **Telegram Stars — не для еды** | ✅ подтверждено | Stars — только цифровые товары/услуги ([telegram.org/blog/telegram-stars](https://telegram.org/blog/telegram-stars)). |
| 8 | **Свой канал продаж без агрегаторов — правильный фокус** | ✅ подтверждено | Комиссии агрегаторов в КЗ кратно выше: Glovo ~30% (с доставкой)/15%, Wolt ~20%+сборы, Яндекс Еда — по оценкам 30–50% с рекламой ([finratings.kz](https://finratings.kz/news/15890-kazakhstantsam-pokazali-skolko-na-samom-dele-zabiraiut-servisy-dostavki-glovo-wolt-i-iandeks-eda/), [merchant.wolt.com](https://merchant.wolt.com/ru-kz/kaz/learning-center/wolt-merchant-fees-and-commissions)). |
| 9 | **Бэклог: отмена клиентом + повторный заказ** (критерий «0 потерянных…», UX) | ✅ реализуемо сейчас | Статус-машина уже допускает `created → cancelled`; окно отмены расширено до `awaiting_prepayment` (пока чек не прислан). Повторный заказ — перенос снапшотов `order_items` в корзину с пропуском стоп-листа. **Реализовано в эксперименте exp/user-cancel-reorder.** |
| 10 | **Автораспознавание чеков Kaspi** (фаза 3) | ✅ уточнено | Рабочая схема: QR в PDF-чеке (pyzbar/OpenCV, ~95%) + OCR + проверка по фискальному API РК; готовые сервисы ProverkaCheka.kz (от 9 990 ₸/мес), PayBot.kz ([sanzharal.kz](https://sanzharal.kz/blog/kaspi-payment-integration-telegram), [proverkacheka.kz](https://proverkacheka.kz/), [paybot.kz](https://paybot.kz/docs)). |

## Рекомендации по роадмапу (фаза 2, после «ок» владельца)

1. **Kaspi Pay для ИП** — подключить в первую очередь (бесплатно): статичный QR + «ссылка для оплаты» в реквизитах бота вместо ручного ввода реквизитов; клиент платит в одно касание, чек-флоу остаётся.
2. **Mini App** — использовать готовый шаблон aiogram-miniapp; 3 экрана (каталог, корзина, чекаут); валидация initData обязательна; нужен домен + HTTPS (есть VPS; домен — вопрос владельца). Платежи — Kaspi-ссылка/QR + ручной чек.
3. **Яндекс Доставка API** — не делать «на вырост»; кнопка-резерв после роста потока.
4. **ИИ-помощник** — идти гибридом: LLM только на свободных вопросах/FAQ/эскалации, оформление — кнопки; DeepSeek API из КЗ платится картой; лимит $10–20/мес покрывает с запасом.
5. **Чеки Kaspi** — сначала ручное подтверждение (текущее), автораспознавание — после роста объёма (QR+OCR+фискальный API, 3–7 дней разработки или SaaS).

## Эксперимент: что сделано тестово (к этому отчёту)

- **exp/user-cancel-reorder**: отмена заказа клиентом (окно: `created` + `awaiting_prepayment` без присланного чека; двухшаговое подтверждение; уведомление группе операторов) и «Заказать снова» в 1 клик (перенос состава в корзину с пропуском стоп-листа) — всё с unit-тестами.
- **scripts/run_test.ps1** — тестовый харнесс из плана (pytest + тестовый бот на БД `delivery_test`).

## Источники

- Kaspi: [business.kaspi.kz/pay](https://business.kaspi.kz/pay/) · [guide.kaspi.kz — подключение ИП](https://guide.kaspi.kz/partner/ru/app/connection/q1381) · [тарифы](https://guide.kaspi.kz/partner/ru/app/conditions/q1445) · [Kaspi webpay partnership](https://kaspi.kz/webpay/partnership) · [гайд Merchant API v2](https://aunimeda.com/blog/kaspi-pay-api-integration-guide) · [оплата в Telegram, КЗ](https://a-lux.kz/blog/priem-oplaty-v-telegram-kaspi-karty-stars/)
- Mini Apps: [core.telegram.org/bots/webapps](https://core.telegram.org/bots/webapps) · [docs.telegram-mini-apps.com](https://docs.telegram-mini-apps.com/platform/getting-app-link) · [шаблон MrConsoleka](https://github.com/MrConsoleka/aiogram-miniapp-template) · [шаблон LEADROI](https://github.com/LEADROI/aiogram-miniapp) · [ресторанный мини-апп OLOT SOMSA](https://github.com/khajiev13/restaurant-mini-app)
- Яндекс Доставка: [delivery.yandex.kz](https://delivery.yandex.kz/ru/) · [dev.go.yandex/services/delivery](https://dev.go.yandex/services/delivery) · [статусы заявки](https://yandex.ru/support/delivery-profile/ru/api/express/claim-process)
- ИИ: [DeepSeek API news](https://api-docs.deepseek.com/news/news250929) · [цены DeepSeek](https://venturebeat.com/technology/deepseeks-new-v3-2-exp-model-cuts-api-pricing-in-half-to-less-than-3-cents/) · [orderflow-ai](https://github.com/ergon73/orderflow-ai) · [aiogram-mcp](https://github.com/py2755/aiogram-mcp)
- Агрегаторы КЗ: [finratings.kz — комиссии](https://finratings.kz/news/15890-kazakhstantsam-pokazali-skolko-na-samom-dele-zabiraiut-servisy-dostavki-glovo-wolt-i-iandeks-eda/) · [Wolt fees](https://merchant.wolt.com/ru-kz/kaz/learning-center/wolt-merchant-fees-and-commissions) · [Яндекс Еда в Павлодаре](https://hard-life.kz/4337-servis-jandeks-eda-zapustilsja-v-pavlodare.html)
- Чеки: [sanzharal — Kaspi + Telegram](https://sanzharal.kz/blog/kaspi-payment-integration-telegram) · [proverkacheka.kz](https://proverkacheka.kz/) · [paybot.kz](https://paybot.kz/docs)
- Telegram Payments: [core.telegram.org/bots/payments](https://core.telegram.org/bots/payments) · [PayBox](https://paybox.kz/) · [Stars](https://telegram.org/blog/telegram-stars)