/**
 * Whether a call record is owned by the current agent.
 *
 * "CDR already answered" must not mean "I am on this call" when the record
 * still names another agent (e.g. queue blind-transfer of a call A already
 * answered). Only the owning agent's answered CDR is evidence of being on_call.
 *
 * Returns false when either id is missing so an unresolved CDR never swallows
 * a ringing UI — prefer showing 来电 over silently skipping it.
 */
export function callRecordBelongsToAgent(
  rec: { last_serving_agent_id?: number | null } | null | undefined,
  myEmployeeId: number | null | undefined,
): boolean {
  if (myEmployeeId == null || rec?.last_serving_agent_id == null) return false
  return rec.last_serving_agent_id === myEmployeeId
}

/**
 * True when this agent's own CDR already shows answered / in progress.
 * Used for SIP handset answer hydrate and similar "I already took this call"
 * paths — never for another agent's answered record on the same call_id.
 */
export function callRecordAnsweredByAgent(
  rec:
    | {
        last_serving_agent_id?: number | null
        first_agent_connected_at?: string | null
        lifecycle_status?: string | null
      }
    | null
    | undefined,
  myEmployeeId: number | null | undefined,
): boolean {
  if (!callRecordBelongsToAgent(rec, myEmployeeId)) return false
  return !!rec?.first_agent_connected_at && rec.lifecycle_status === 'active'
}

/**
 * True when the CDR shows the customer connected — the only record-level
 * answer evidence for an outbound call. started_at exists from creation
 * (the dial time) and must not be treated as an answer.
 */
export function callRecordCustomerConnected(
  rec: { customer_connected_at?: string | null } | null | undefined,
): boolean {
  return Boolean(rec?.customer_connected_at)
}
