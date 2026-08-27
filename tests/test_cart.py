from core.cart import MAX_QTY, change_quantity, clear_cart, get_cart_view
from core.catalog import (
    extract_weight,
    get_product,
    list_active_categories,
    list_available_products,
    product_weight_label,
)
from data.models import Category, Product


async def _seed(session):
    category = Category(name="Тест", sort_order=0, is_active=True)
    session.add(category)
    await session.flush()
    p1 = Product(category_id=category.id, name="Плов", price=1800, is_available=True, sort_order=0)
    p2 = Product(category_id=category.id, name="Манты", price=2500, is_available=True, sort_order=1)
    p3 = Product(category_id=category.id, name="Скрытый", price=100, is_available=False, sort_order=2)
    session.add_all([p1, p2, p3])
    await session.commit()
    return category.id, p1.id, p2.id, p3.id


async def test_catalog_lists_only_available(db_session):
    cid, p1, p2, p3 = await _seed(db_session)
    cats = await list_active_categories(db_session)
    assert [c.id for c in cats] == [cid]
    products = await list_available_products(db_session, cid)
    assert [p.id for p in products] == [p1, p2]
    assert (await get_product(db_session, p3)).is_available is False


def test_extract_weight_from_description():
    assert extract_weight("помидоры, лук и специи, 0,5 кг") == "0,5 кг"
    assert extract_weight("Лёгкий овощной салат, 0.5 кг") == "0,5 кг"
    assert extract_weight("500 г") == "500 г"
    assert extract_weight("10-12 шт") == "10-12 шт"
    assert extract_weight("только овощи") is None
    assert extract_weight(None) is None


def test_product_weight_label_no_duplicate():
    # вес и так в названии — суффикс из описания не нужен
    assert product_weight_label("Плов Ханский (3 кг)", "плова, 3 кг") is None
    # вес только в описании — показываем
    assert product_weight_label("Цезарь", "Курица, соус, сухарики 0,5 кг") == "0,5 кг"
    assert product_weight_label("Ачучук", None) is None


async def test_cart_add_decrement_remove(db_session):
    cid, p1, p2, p3 = await _seed(db_session)
    assert await change_quantity(db_session, user_id=1, product_id=p1, delta=1) == 1
    assert await change_quantity(db_session, user_id=1, product_id=p1, delta=1) == 2
    assert await change_quantity(db_session, user_id=1, product_id=p1, delta=-1) == 1
    assert await change_quantity(db_session, user_id=1, product_id=p3, delta=1) == 1
    view = await get_cart_view(db_session, 1)
    assert len(view.rows) == 2
    # удаление позиции при 0
    assert await change_quantity(db_session, user_id=1, product_id=p1, delta=-1) == 0
    view = await get_cart_view(db_session, 1)
    assert [r.product_id for r in view.rows] == [p3]


async def test_cart_view_total_excludes_unavailable(db_session):
    cid, p1, p2, p3 = await _seed(db_session)
    await change_quantity(db_session, 1, p1, 2)  # 2 × 1800
    await change_quantity(db_session, 1, p2, 1)  # 1 × 2500
    await change_quantity(db_session, 1, p3, 1)  # недоступный — в корзине, но не в сумме
    view = await get_cart_view(db_session, 1)
    assert view.total == 2 * 1800 + 2500
    assert view.unavailable_total == 100
    assert len(view.rows) == 3
    assert view.rows[2].available is False


async def test_cart_quantity_capped(db_session):
    cid, p1, p2, p3 = await _seed(db_session)
    for _ in range(MAX_QTY + 5):
        await change_quantity(db_session, 1, p1, 1)
    view = await get_cart_view(db_session, 1)
    assert view.rows[0].quantity == MAX_QTY


async def test_cart_clear(db_session):
    cid, p1, p2, p3 = await _seed(db_session)
    await change_quantity(db_session, 1, p1, 1)
    await change_quantity(db_session, 1, p2, 2)
    await clear_cart(db_session, 1)
    view = await get_cart_view(db_session, 1)
    assert view.rows == []
    assert view.total == 0