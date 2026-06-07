export const BRANCH_CHIP_WIDTH = 134
export const BRANCH_ADD_WIDTH = 132
export const BRANCH_GAP_X = 12
export const BRANCH_PADDING_X = 4

export function branchColumnsWidth(branchCount: number): number {
  return branchCount * BRANCH_CHIP_WIDTH + Math.max(0, branchCount - 1) * BRANCH_GAP_X
}

export function branchColumnsCenterX(branchCount: number): number {
  return BRANCH_PADDING_X + branchColumnsWidth(branchCount) / 2
}

export function branchNodeWidth(branchCount: number): number {
  return branchColumnsWidth(branchCount) + BRANCH_ADD_WIDTH + BRANCH_GAP_X + 2 * BRANCH_PADDING_X
}
