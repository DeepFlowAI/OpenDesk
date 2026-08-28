'use client'

import { useState } from 'react'

import { CallRecordDetailDrawer } from '@/app/components/features/call-center/call-record-detail-drawer'
import { CallRecordFilterBar } from '@/app/components/features/call-center/call-record-filter-bar'
import { CallRecordTable } from '@/app/components/features/call-center/call-record-table'
import { useCallRecordList } from '@/app/components/features/call-center/use-call-record-list'
import { WorkspaceColumnsDrawer } from '@/components/workspace/columns-drawer'

export default function CallRecordsPage() {
  const list = useCallRecordList()
  const [moreExpanded, setMoreExpanded] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const data = list.records.data

  return (
    <div className="flex h-full min-w-0 flex-col">
      <CallRecordFilterBar
        locale={list.locale}
        draft={list.draft}
        onChange={list.setDraft}
        onSearch={list.apply}
        searching={list.records.isFetching}
        onReset={() => { list.reset(); setMoreExpanded(false) }}
        options={list.filterOptions}
        canFilterByOwnership={list.canFilterByOwnership}
        moreFilterCount={list.moreFilterCount}
        expanded={moreExpanded}
        onExpandedChange={setMoreExpanded}
        canExport={list.canExport}
        exporting={list.exporting}
        onExport={list.exportRecords}
        onColumns={() => list.setColumnsOpen(true)}
        hasColumnOverride={list.hasColumnOverride}
      />
      <CallRecordTable
        locale={list.locale}
        items={data?.items ?? []}
        columns={list.visibleColumns}
        loading={list.records.isLoading}
        fetching={list.records.isFetching}
        error={list.records.isError}
        hasActiveFilters={list.hasActiveFilters}
        onRetry={() => list.records.refetch()}
        onSelect={setOpenId}
        total={data?.total ?? 0}
        pages={data?.pages ?? 0}
        page={list.page}
        perPage={list.perPage}
        onPageChange={list.setPage}
        onPerPageChange={(perPage) => { list.setPerPage(perPage); list.setPage(1) }}
      />
      {list.columnsOpen && (
        <WorkspaceColumnsDrawer
          locale={list.locale}
          fields={list.columnFields}
          baselineConfig={null}
          currentOverride={list.columnConfig}
          requiredFieldKeys={['customer_number']}
          onApply={list.saveColumns}
          onReset={list.resetColumns}
          onClose={() => list.setColumnsOpen(false)}
        />
      )}
      {openId && <CallRecordDetailDrawer recordId={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}
