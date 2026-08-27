import pytest
from sqlalchemy import select

from core import admin as admin_srv
from core.catalog import list_active_categories, list_available_products
from data.models import Category, Product


async def test_category_crud(db_session):
    cat = await admin_srv.add_category(db_session, "Пловы")
    assert cat.is_active is True
    assert await admin_srv.rename_category(db_session, cat.id, "Плов и рис") is not None
    renamed = await db_session.get(Category, cat.id)
    assert renamed.name == "Плов и рис"
    # скрытие
    state = await admin_srv.toggle_category(db_session, cat.id)
    assert state is False
    cats = await list_active_categories(db_session)
    assert cats == []  # скрытая не видна клиентам
    state = await admin_srv.toggle_category(db_session, cat.id)
    assert state is True
    # удаление пустой
    assert await admin_srv.delete_category_if_empty(db_session, cat.id) is True


async def test_category_delete_blocked_with_products(db_session):
    cat = await admin_srv.add_category(db_session, "Пловы")
    await admin_srv.add_product(db_session, cat.id, "Плов", 1800)
    assert await admin_srv.delete_category_if_empty(db_session, cat.id) is False
    assert await db_session.get(Category, cat.id) is not None


async def test_product_crud(db_session):
    cat = await admin_srv.add_category(db_session, "Пловы")
    product = await admin_srv.add_product(db_session, cat.id, "Плов", 1800, "Рис и баранина")
    assert product.photo_file_id is None
    await admin_srv.update_product(db_session, product.id, price=1900, photo_file_id="AgC123")
    fresh = await db_session.get(Product, product.id)
    assert fresh.price == 1900
    assert fresh.photo_file_id == "AgC123"
    # стоп-лист
    assert await admin_srv.toggle_product(db_session, product.id) is False
    assert await list_available_products(db_session, cat.id) == []
    assert await admin_srv.toggle_product(db_session, product.id) is True
    # удаление
    await admin_srv.delete_product(db_session, product.id)
    assert await db_session.get(Product, product.id) is None


async def test_category_and_product_ordering(db_session):
    c1 = await admin_srv.add_category(db_session, "А")
    c2 = await admin_srv.add_category(db_session, "Б")
    c3 = await admin_srv.add_category(db_session, "В")
    await admin_srv.move_category(db_session, c3.id, -1)  # В вверх
    cats = list(await db_session.scalars(select(Category).order_by(Category.sort_order, Category.id)))
    assert [c.name for c in cats] == ["А", "В", "Б"]

    p1 = await admin_srv.add_product(db_session, c1.id, "x", 100)
    p2 = await admin_srv.add_product(db_session, c1.id, "y", 200)
    p3 = await admin_srv.add_product(db_session, c1.id, "z", 300)
    await admin_srv.move_product(db_session, p3.id, -1)
    await admin_srv.move_product(db_session, p3.id, -1)  # z вверх дважды
    products = list(await db_session.scalars(select(Product).where(Product.category_id == c1.id).order_by(Product.sort_order, Product.id)))
    assert [p.name for p in products] == ["z", "x", "y"]