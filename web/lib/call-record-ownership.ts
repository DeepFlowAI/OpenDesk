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
  rec: { agent_id?: number | null } | null | undefined,
  myEmployeeId: number | null | undefined,
): boolean {
  if (myEmployeeId == null || rec?.agent_id == null) return false
  return rec.agent_id === myEmployeeId
}

/**
 * True when this agent's own CDR already shows answered / in progress.
 * Used for SIP handset answer hydrate and similar "I already took this call"
 * paths — never for another agent's answered record on the same call_id.
 */
export function callRecordAnsweredByAgent(
  rec:
    | {
        agent_id?: number | null
        answered_at?: string | null
        state?: string | null
      }
    | null
    | undefined,
  myEmployeeId: number | null | undefined,
): boolean {
  if (!callRecordBelongsToAgent(rec, myEmployeeId)) return false
  return !!rec?.answered_at || rec?.state === 'in_progress'
}
