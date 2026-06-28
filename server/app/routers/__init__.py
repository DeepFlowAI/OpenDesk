from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    from app.routers.v1 import (
        health,
        system_info,
        auth,
        system_settings,
        open_agent_settings,
        service_hours,
        api_keys,
        open_api,
        open_knowledge,
        roles,
        employees,
        upload,
        employee_groups,
        system_users,
        voice_flows,
        ticket_workflows,
        inbound_routing_rules,
        session_routing_rules,
        conversation_settings,
        channels,
        knowledge,
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(system_info.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(system_settings.router, prefix="/api/v1")
    app.include_router(open_agent_settings.router, prefix="/api/v1")
    app.include_router(service_hours.router, prefix="/api/v1")
    app.include_router(api_keys.router, prefix="/api/v1")
    app.include_router(open_api.router, prefix="/api/v1")
    app.include_router(open_knowledge.router, prefix="/api/v1")
    app.include_router(roles.router, prefix="/api/v1")
    app.include_router(employees.router, prefix="/api/v1")
    app.include_router(upload.router, prefix="/api/v1")
    app.include_router(employee_groups.router, prefix="/api/v1")
    app.include_router(system_users.router, prefix="/api/v1")
    app.include_router(voice_flows.router, prefix="/api/v1")
    app.include_router(ticket_workflows.router, prefix="/api/v1")
    app.include_router(inbound_routing_rules.router, prefix="/api/v1")
    app.include_router(session_routing_rules.router, prefix="/api/v1")
    app.include_router(conversation_settings.router, prefix="/api/v1")
    app.include_router(channels.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    # Tenant CRUD endpoints are provided by an optional tenant-management
    # extension (see app.extensions). Single-tenant deployments rely on the
    # auto-provisioned default tenant from app.db.seed instead.

    from app.routers.v1 import conversations, public, session_records, field_definitions, transfer, conversation_collaboration, offline_messages, queue_workspace, telemetry
    app.include_router(conversations.file_router, prefix="/api/v1")
    app.include_router(conversations.router, prefix="/api/v1")
    app.include_router(conversations.agent_router, prefix="/api/v1")
    app.include_router(public.router, prefix="/api/v1")
    app.include_router(telemetry.router, prefix="/api/v1")
    app.include_router(session_records.router, prefix="/api/v1")
    app.include_router(field_definitions.router, prefix="/api/v1")
    app.include_router(transfer.router, prefix="/api/v1")
    app.include_router(conversation_collaboration.router, prefix="/api/v1")
    app.include_router(offline_messages.router, prefix="/api/v1")
    app.include_router(queue_workspace.router, prefix="/api/v1")

    from app.routers.v1 import form_layouts, interaction_rules, session_summary, call_summary, user_views, ticket_views, organization_views, users, organizations, tickets, call_center, queue
    app.include_router(call_center.router, prefix="/api/v1")
    app.include_router(queue.router, prefix="/api/v1")
    app.include_router(form_layouts.router, prefix="/api/v1")
    app.include_router(interaction_rules.router, prefix="/api/v1")
    app.include_router(session_summary.router, prefix="/api/v1")
    app.include_router(call_summary.router, prefix="/api/v1")
    app.include_router(user_views.router, prefix="/api/v1")
    app.include_router(ticket_views.router, prefix="/api/v1")
    app.include_router(organization_views.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(organizations.router, prefix="/api/v1")
    app.include_router(tickets.router, prefix="/api/v1")
