-- Full root-to-leaf category id path per product (JSON array of ints),
-- alongside the existing single-leaf products.category_id -- see
-- client/normalize.py:parse_category_ancestor_ids and
-- dashboard/categories.py. Needed because AliExpress's category-name
-- lookup (categories table, 0003_categories.sql) only covers a much
-- broader/shallower tree than real per-product leaf category ids;
-- resolving a display name needs to be able to fall back through a
-- product's own ancestor chain, not just try the leaf id alone.
ALTER TABLE products ADD COLUMN category_ancestor_ids TEXT;
