from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    from app.routers.v1 import (
        health,
        system_info,
        auth,
        system_settings,
        service_hours,
        employees,
        upload,
        employee_groups,
        system_users,
        voice_flows,
        inbound_routing_rules,
        session_routing_rules,
        conversation_settings,
        channels,
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(system_info.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(system_settings.router, prefix="/api/v1")
    app.include_router(service_hours.router, prefix="/api/v1")
    app.include_router(employees.router, prefix="/api/v1")
    app.include_router(upload.router, prefix="/api/v1")
    app.include_router(employee_groups.router, prefix="/api/v1")
    app.include_router(system_users.router, prefix="/api/v1")
    app.include_router(voice_flows.router, prefix="/api/v1")
    app.include_router(inbound_routing_rules.router, prefix="/api/v1")
    app.include_router(session_routing_rules.router, prefix="/api/v1")
    app.include_router(conversation_settings.router, prefix="/api/v1")
    app.include_router(channels.router, prefix="/api/v1")
    # Tenant CRUD endpoints are provided by an optional tenant-management
    # extension (see app.extensions). Single-tenant deployments rely on the
    # auto-provisioned default tenant from app.db.seed instead.

    from app.routers.v1 import conversations, public, session_records, field_definitions, transfer
    app.include_router(conversations.router, prefix="/api/v1")
    app.include_router(conversations.agent_router, prefix="/api/v1")
    app.include_router(public.router, prefix="/api/v1")
    app.include_router(session_records.router, prefix="/api/v1")
    app.include_router(field_definitions.router, prefix="/api/v1")
    app.include_router(transfer.router, prefix="/api/v1")

    from app.routers.v1 import form_layouts, interaction_rules, session_summary, user_views, ticket_views, organization_views, users, organizations, tickets
    app.include_router(form_layouts.router, prefix="/api/v1")
    app.include_router(interaction_rules.router, prefix="/api/v1")
    app.include_router(session_summary.router, prefix="/api/v1")
    app.include_router(user_views.router, prefix="/api/v1")
    app.include_router(ticket_views.router, prefix="/api/v1")
    app.include_router(organization_views.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(organizations.router, prefix="/api/v1")
    app.include_router(tickets.router, prefix="/api/v1")
