# ADR-002 · 数据集：Olist Brazilian E-Commerce（公开数据）

- 状态：已接受（2026-11-24）

## 决策
使用 Kaggle 公开数据集 `olistbr/brazilian-ecommerce`（CC BY-NC-SA 4.0，非商业用途）。

## 理由
- 9 张真实关联表、约 10 万订单，含脏数据、一单多商品、多次支付、葡语品类等真实难点。
- 天然支持 GMV、履约、评价、复购、地域 / 品类归因等分析场景。

## 获取方式（二选一）
1. 浏览器登录 Kaggle 手动下载 zip，放到 `data/raw/olist.zip`。
2. 配置 Kaggle API Token（`%USERPROFILE%\.kaggle\kaggle.json`）后由 `scripts/download_data.py` 下载。

## 后果
- 原始数据不入 Git（`.gitignore`），以脚本 + 行数校验保证可复现。
- 仅限学习 / 作品集用途，README 中注明许可与出处。
