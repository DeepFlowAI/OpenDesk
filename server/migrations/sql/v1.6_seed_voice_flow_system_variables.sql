-- Voice flow system variable seed (v1.6)
-- Idempotent — safe to re-run.
-- Also seeded by Alembic migration 5a1c2d3e4f5b; this script lets ops re-apply
-- without running migrations (e.g. when the prod DB is already at head).

INSERT INTO voice_flow_system_variables
    (name, display_name_zh, display_name_en, value_type, description_zh, description_en, sort_order)
VALUES
    ('sys.caller_number', '用户号码', 'Caller Number', 'text',
     '当前来电的主叫号码（E.164 格式）', 'Inbound caller number (E.164)', 10),
    ('sys.called_number', '服务号码', 'Called Number', 'text',
     '当前来电的被叫号码（企业对外服务号码）', 'Inbound called/service number', 20),
    ('sys.current_time', '当前时间', 'Current Time', 'time',
     '流程执行到该节点时的服务器时间', 'Server time when the node executes', 30)
ON CONFLICT (name) DO UPDATE SET
    display_name_zh = EXCLUDED.display_name_zh,
    display_name_en = EXCLUDED.display_name_en,
    value_type      = EXCLUDED.value_type,
    description_zh  = EXCLUDED.description_zh,
    description_en  = EXCLUDED.description_en,
    sort_order      = EXCLUDED.sort_order;
