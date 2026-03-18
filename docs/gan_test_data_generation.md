# Генерация тестовых данных через GAN

## 1) Выбранная GAN
- Модель: CTGAN (Conditional Tabular GAN).
- Почему: хорошо работает с табличными смешанными признаками (категориальные + числовые), подходит для ecommerce событий.

## 2) Промпт для формирования набора данных
Используемый промпт (шаблон):

```text
Сгенерируй синтетические записи взаимодействий для ecommerce.
Ограничения:
1) Используй только product_id, существующие в таблице products.
2) event_type только из: view, add_to_cart, purchase, click_recommendation, remove_from_cart.
3) implicit_weight должен соответствовать маппингу: view=1, click_recommendation=2, add_to_cart=3, purchase=10, remove_from_cart=-1.
4) user_id может быть NULL только если заполнен session_id.
5) placement только из: main, cart, product_card, search, recommendation_block, checkout.
6) Для заказов каждый order_id должен содержать минимум 2 разных product_id.
7) category_id и product_popularity должны соответствовать данным products.
```

## 3) Формирование набора данных
Скрипт: [scripts/generate_gan_test_data.py](scripts/generate_gan_test_data.py)

Что делает:
- обучает CTGAN на текущих данных `ml_training_interactions`;
- генерирует синтетические взаимодействия и записывает их в `ml_training_interactions`;
- генерирует синтетические заказы (`orders` + `order_items`), при этом каждый заказ содержит минимум 2 товара;
- использует только существующие товары из `products`;
- добавляет события `purchase` в `ml_training_interactions` для созданных заказов.

### Запуск

```bash
python scripts/generate_gan_test_data.py --interactions 1500 --orders 300 --epochs 100 --seed 42
```

Для просмотра шаблона промпта:

```bash
python scripts/generate_gan_test_data.py --show-prompt
```

## Примечания
- Если данных мало, скрипт использует bootstrap-расширение выборки перед обучением CTGAN.
- Для воспроизводимости используйте фиксированный `--seed`.
