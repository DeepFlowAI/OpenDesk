-- Assign queue system variable seed (v4.3)
-- Idempotent — safe to re-run.

INSERT INTO voice_flow_system_variables
    (name, display_name_zh, display_name_en, value_type, description_zh, description_en, sort_order)
VALUES
    ('sys.assign_queue_status', '分配队列状态', 'Assign Queue Status', 'text',
     '最近一次分配队列节点的失败状态，可用于 timeout 出口后的信息判定',
     'Failure status from the latest assign queue node for timeout-branch conditions', 40),
    ('sys.assign_queue_limit_reason', '分配队列上限原因', 'Assign Queue Limit Reason', 'text',
     '达到排队上限时的原因：max_waiting_count、max_wait_seconds 或 mixed_limit',
     'Queue limit reason: max_waiting_count, max_wait_seconds, or mixed_limit', 50)
ON CONFLICT (name) DO UPDATE SET
    display_name_zh = EXCLUDED.display_name_zh,
    display_name_en = EXCLUDED.display_name_en,
    value_type      = EXCLUDED.value_type,
    description_zh  = EXCLUDED.description_zh,
    description_en  = EXCLUDED.description_en,
    sort_order      = EXCLUDED.sort_order;
