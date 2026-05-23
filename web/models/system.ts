export type SystemEdition = 'community' | 'enterprise'

export type SystemInfo = {
  app_name: string
  app_version: string
  edition: SystemEdition
  /** UX hint: hide the tenant field on the login form when true. Defaults
   *  to true on OSS deployments (tenants extension absent). */
  single_tenant_mode: boolean
  /** Tenant slug to auto-fill when single_tenant_mode is true. */
  default_tenant_id: string
  /** Whether the enterprise reports module (session reports + online monitor)
   *  is available in this build. Drives the records sub-nav visibility. */
  reports_enabled: boolean
}
