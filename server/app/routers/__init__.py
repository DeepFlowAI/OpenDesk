from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    from app.routers.v1 import (
        health,
        exports,
        system_info,
        auth,
        system_settings,
        open_agent_settings,
        voice_speed,
        service_hours,
        api_keys,
        event_subscriptions,
        open_api,
        open_knowledge,
        open_engagement,
        roles,
        employees,
        upload,
        employee_groups,
        system_users,
        voice_flows,
        satisfaction_flows,
        ticket_workflows,
        custom_dashboards,
        inbound_routing_rules,
        session_routing_rules,
        conversation_settings,
        lingomaster,
        channels,
        knowledge,
        scheduling,
        quality_scorecards,
        quality_plans,
        quality_reviews,
    )

    app.include_router(exports.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(system_info.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(system_settings.router, prefix="/api/v1")
    app.include_router(open_agent_settings.router, prefix="/api/v1")
    app.include_router(voice_speed.router, prefix="/api/v1")
    app.include_router(service_hours.router, prefix="/api/v1")
    app.include_router(api_keys.router, prefix="/api/v1")
    app.include_router(event_subscriptions.router, prefix="/api/v1")
    app.include_router(open_api.router, prefix="/api/v1")
    app.include_router(open_knowledge.router, prefix="/api/v1")
    app.include_router(open_engagement.router, prefix="/api/v1")
    app.include_router(roles.router, prefix="/api/v1")
    app.include_router(employees.router, prefix="/api/v1")
    app.include_router(upload.router, prefix="/api/v1")
    app.include_router(employee_groups.router, prefix="/api/v1")
    app.include_router(system_users.router, prefix="/api/v1")
    app.include_router(voice_flows.router, prefix="/api/v1")
    app.include_router(satisfaction_flows.router, prefix="/api/v1")
    app.include_router(ticket_workflows.router, prefix="/api/v1")
    app.include_router(custom_dashboards.router, prefix="/api/v1")
    app.include_router(custom_dashboards.workspace_router, prefix="/api/v1")
    app.include_router(custom_dashboards.run_router, prefix="/api/v1")
    app.include_router(inbound_routing_rules.router, prefix="/api/v1")
    app.include_router(session_routing_rules.router, prefix="/api/v1")
    app.include_router(conversation_settings.router, prefix="/api/v1")
    app.include_router(lingomaster.router, prefix="/api/v1")
    app.include_router(channels.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(scheduling.router, prefix="/api/v1")
    app.include_router(quality_scorecards.router, prefix="/api/v1")
    app.include_router(quality_plans.router, prefix="/api/v1")
    app.include_router(quality_reviews.router, prefix="/api/v1")
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

    from app.routers.v1 import form_layouts, interaction_rules, session_summary, call_summary, user_views, ticket_views, organization_views, users, organizations, tickets, call_center, call_center_sms, embedded_call, sms_callback, learning_admin, learning_callback, learning_my, learning_exam_admin, learning_exam_my, queue, engagement, engagement_sms_tasks, sip_extensions
    from app.routers.v1 import call_event_subscriptions, call_event_tester, open_call_center
    app.include_router(call_event_subscriptions.router, prefix="/api/v1")
    app.include_router(call_event_tester.router, prefix="/api/v1")
    app.include_router(call_event_tester.public_router, prefix="/api/v1")
    app.include_router(open_call_center.router, prefix="/api/v1")
    app.include_router(call_center.router, prefix="/api/v1")
    app.include_router(call_center_sms.router, prefix="/api/v1")
    app.include_router(embedded_call.router, prefix="/api/v1")
    app.include_router(sms_callback.router, prefix="/api/v1")
    app.include_router(learning_admin.router, prefix="/api/v1")
    app.include_router(learning_callback.router, prefix="/api/v1")
    app.include_router(learning_my.router, prefix="/api/v1")
    app.include_router(learning_exam_admin.router, prefix="/api/v1")
    app.include_router(learning_exam_my.router, prefix="/api/v1")
    app.include_router(sip_extensions.router, prefix="/api/v1")
    app.include_router(sip_extensions.device_router, prefix="/api/v1")
    app.include_router(queue.router, prefix="/api/v1")
    app.include_router(engagement.router, prefix="/api/v1")
    app.include_router(engagement_sms_tasks.router, prefix="/api/v1")
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
