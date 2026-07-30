-- 只在数据库 opermind_demo 的 opermind_demo schema 中执行。
-- 此文件不引用、也不操作任何既有业务库或 gongkar 表。

CREATE SCHEMA opermind_demo;

CREATE TABLE opermind_demo.orders (
    id BIGSERIAL PRIMARY KEY,
    order_no VARCHAR(32) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
