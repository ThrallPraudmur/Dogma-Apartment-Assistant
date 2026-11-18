# Данные

- apartments.json — метаданные выгрузки и массив apartments.
- apartments.sqlite — те же квартиры в таблице apartments.
- summary.json — количество, ЖК и диапазоны значений.
- example_response.json — реальный top-3 по параметрам: ЖК ГРЕЙД, до 7 млн, от 30 м² (без ограничения комнат).

Проверяйте metadata.complete: false означает, что строгая проверка полноты не пройдена, например каталог изменился во время обхода. См. count_changed, duplicates и reported_count. Даже complete=true не гарантирует неизменность каталога после выгрузки.
