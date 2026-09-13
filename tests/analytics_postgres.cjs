/* Local PostgreSQL (WASM), synthetic data only. No production connection. */
const {PGlite} = require('../.validation/node_modules/@electric-sql/pglite');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
    const db = new PGlite();
    const sql = JSON.parse(fs.readFileSync('.validation/analytics-sql.json', 'utf8').replace(/^\uFEFF/, ''));
    await db.exec(`
        CREATE TABLE businesses (id integer PRIMARY KEY, name text);
        CREATE TABLE products (id integer PRIMARY KEY, name text, business_id integer);
        CREATE TABLE orders (id integer PRIMARY KEY, business_id integer, status text, total_amount numeric, created_at timestamp);
        CREATE TABLE order_items (id integer PRIMARY KEY, order_id integer, product_id integer, quantity integer);
    `);
    await assert.rejects(db.query(sql.before[2]), error => {
        console.log('BEFORE:', error.code, error.message);
        return error.code === '42803' && error.message.includes('businesses.name');
    });
    for (const query of sql.after) assert.deepEqual((await db.query(query)).rows, []);
    await db.exec(`
        INSERT INTO businesses VALUES (1, 'A'), (2, 'B'), (3, 'No sales');
        INSERT INTO products VALUES (1, 'Same name', 1), (2, 'Same name', 2), (3, 'Unsold', 1);
        INSERT INTO orders VALUES (1, 1, 'delivered', 100, now()), (2, 2, 'delivered', 700, now()),
            (3, 1, 'cancelled', 5000, now()), (4, 2, 'delivered', NULL, now()), (5, 3, NULL, NULL, NULL);
        INSERT INTO order_items VALUES (1, 1, 1, 2), (2, 2, 2, 7), (3, 3, 1, 99),
            (4, 4, 2, NULL), (5, 1, 2, 400);
    `);
    const [revenue, daily, products, statuses] = await Promise.all(sql.after.map(query => db.query(query)));
    assert.equal(Number(revenue.rows.find(row => row.business_id === 1).revenue), 100);
    assert.equal(Number(revenue.rows.find(row => row.business_id === 2).revenue), 700);
    assert.equal(Number(revenue.rows.find(row => row.business_id === 3).revenue), 0);
    assert.equal(Number(daily.rows[0].order_count), 4);
    assert.equal(Number(products.rows.find(row => row.business_id === 1).sold), 2);
    assert.equal(Number(products.rows.find(row => row.business_id === 2).sold), 7);
    assert.equal(products.rows.length, 2);
    assert.equal(statuses.rows.length, 3);
    console.log('AFTER: all four actual ORM queries pass on PostgreSQL; empty, multiple businesses, NULL, cancelled and corrupt cross-business rows covered.');
    await db.close();
})().catch(error => { console.error(error); process.exitCode = 1; });
