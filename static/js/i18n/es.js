window.i18n.global.mergeLocaleMessage('es', {
  events: {
    new_event: 'Nuevo evento',

    events_title: 'Eventos',

    export_csv: 'Exportar a CSV',

    tickets_title: 'Entradas',

    promo_codes: 'Códigos promocionales',

	no_promo_codes: 'No hay códigos promocionales para este evento.',

    resend_ticket_email: 'Reenviar email de entrada',

    confirm_onchain_payment: 'Confirmar pago onchain',

    extension_title: 'Extensión de Eventos',

    info_label: 'Info',

    extension_desc_title:
      'Eventos: Vender y registrar entradas para un evento',

    extension_desc:
      'Eventos te permite crear tipos de entradas para un evento. Cada entrada es un código QR único que el usuario presenta al registrarse. Eventos incluye un escáner de entradas compartible que puede usarse para registrar asistentes.',

    created_by: 'Creado por,',

    swagger_api: 'Swagger API',

    event_title_label: 'Título del evento',

    wallet_label: 'Cartera *',

    event_info_label: 'Información sobre el evento',

    markdown_supported: 'Soporta Markdown',

    image_url_label: 'URL de imagen',

    image_url_hint:
      'Imagen de banner opcional para mostrar en la página del evento',

    event_begins: 'El evento comienza',

    event_ends: 'El evento termina',

    opening_date_label: 'Fecha de apertura de entradas',

  
    currency_unit: 'Unidad monetaria',

    amount_tickets_label: 'Cantidad de entradas',

    price_label: 'Precio ({currency}) *',

    use_ticket_image: 'Usar imagen de entrada',

    download_template: 'Descargar plantilla',

    replace_template: 'Reemplazar',

    custom_template_uploaded: 'Plantilla de entrada personalizada subida.',

    payment_methods: 'Métodos de Pago',

    lightning: 'Lightning',

    fiat: 'Fiat',

    onchain: 'Onchain',

    ln_wallet_label: 'Monedero LN',

    onchain_wallet_label: 'Monedero Onchain',

    onchain_disabled_hint: 'La extensión Onchain Wallet (WatchOnly) debe estar activada y tener un monedero.',

    fiat_provider_hint: 'Los proveedores fiat deben configurarse en los ajustes del servidor LNbits y tu usuario debe estar autorizado.',

    fiat_provider_label: 'Proveedor Fiat',

  
    conditional_events_title: 'Eventos condicionales',

    conditional_events_desc:
      'Haz este evento condicional si se vende un mínimo de entradas. Se pedirá al usuario que proporcione una dirección Lightning o LNURL pay para reembolsos.',

    conditional_event_label: 'Evento condicional',

    min_tickets_label: 'Entradas mínimas',

    ticket_delivery_title: 'Entrega de entradas',

    ticket_delivery_desc:
      'Envía el enlace de la entrada pagada automáticamente por email o Nostr DM.',

    email_notifications: 'Notificaciones por email',

    email_not_configured: 'Email no configurado en ajustes de LNbits',

    nostr_notifications: 'Notificaciones por Nostr',

    nostr_not_configured: 'Nostr no configurado en ajustes de LNbits',

    notification_subject_label: 'Asunto de notificación de entrada',

    notification_subject_hint:
      'Se usa como asunto del email al enviar enlaces de entradas pagadas.',

    notification_body_label: 'Cuerpo de notificación de entrada',

    notification_body_hint:
      'Se muestra antes del enlace de entrada en la notificación.',

    onchain_payments: 'Pagos onchain',

    onchain_desc:
      'Aceptar pagos Bitcoin onchain. Requiere las extensiones SatsPay y Watchonly instaladas y habilitadas.',

    accept_onchain: 'Aceptar pagos onchain',

    watchonly_wallet: 'Cartera watchonly',

    watchonly_wallet_hint:
      'Cartera Bitcoin watchonly para recibir pagos onchain',

    onchain_zeroconf: 'Zero-conf (aceptar transacciones no confirmadas)',

    onchain_fasttrack: 'Fasttrack (tratar pendientes como pagados)',

    update_event: 'Actualizar evento',

    create_event: 'Crear evento',

    promo_code_label: 'Código promocional',

    promo_code_required: 'Se requiere un código de oferta a menos que esta regla también requiera un ID de entrada.',

    active: 'Activo',

    inactive: 'Inactivo',

	discount_label: 'Descuento (%)',

	add_promo_code: 'Añadir código promocional',

	edit_promo_code: 'Editar código promocional',

	promo_code_exists: 'Este código promocional ya existe.',

	save: 'Guardar',

    email_resent: 'Email de entrada reenviado.',

    email_resend_failed: 'Email de entrada fallido: {error}',

    nostr_resent: 'Nostr DM de entrada reenviado.',

    nostr_resend_failed: 'Nostr DM de entrada fallido: {error}',

    unknown_error: 'Error desconocido.',

    onchain_confirmed: 'Pago onchain confirmado.',

    ticket_template_uploaded: 'Plantilla de entrada subida.',

    promo_codes_updated: 'Códigos promocionales actualizados.',

    delete_ticket_confirm: '¿Está seguro de que quiere eliminar esta entrada?',

    delete_event_confirm: '¿Está seguro de que quiere eliminar este evento?',

    event_canceled_notify:
      'El evento {name} ha sido cancelado y se han emitido reembolsos.',

    col_name: 'Nombre',

    col_start_date: 'Fecha de inicio',

    col_end_date: 'Fecha de fin',

    col_canceled: 'Cancelado',

    col_event: 'Evento',

    col_registered: 'Registrado',

    col_nostr: 'Nostr',

    col_deactivated: 'Desactivado',

    col_promo_code: 'Código promocional',

    col_satspay: 'Pago',

    col_yes: 'Sí',

    col_no: 'No',

    submit: 'Enviar',

    promo_code_optional: '(opcional) Código promocional',

    buy_ticket: 'Comprar entrada',

    your_name_label: 'Tu nombre (opcional)',

    your_email_label: 'Tu email',

    your_email_delivery_label: 'Su email (entrega de tickets, opcional)',

    required: '* Obligatorio',

    nostr_nip05_label: 'Su Nostr NIP-05 (entrega de tickets, opcional)',

    nostr_nip05_hint: '',

    refund_label: 'Lnaddress o LNURL de reembolso',

    refund_hint:
      'Si no se alcanzan las entradas mínimas ({min_tickets}), se enviará un reembolso.',

    link_to_ticket: '¡Enlace a tu entrada!',

    continue_to_checkout: 'Continuar al pago',

    fiat_checkout_opened:
      'Tu pago fiat se ha abierto en una nueva pestaña. Si no es así, usa el botón de abajo.',

    go_to_checkout: 'Ir al pago',

    copy_payment_link: 'Copiar enlace de pago',

    copy_invoice: 'Copiar factura',

    event_unavailable: 'Evento no disponible.',

    name_validation:
      'Por favor ingresa un nombre válido. No se permiten caracteres especiales.',

    email_validation: 'Por favor ingresa un email válido.',

    waiting_for_payment: 'Esperando pago...',

    payment_sent: '¡Enviado, gracias!',

    payment_lightning: 'Lightning',

    payment_bitcoin: 'Bitcoin',

    payment_fiat: 'Fiat ({unit})',

    registration: 'Registro',

    scan_ticket: 'Escanear entrada',
    checkin_valid: 'Válida — registrar',
    checkin_already: 'Ya registrada',
    checkin_confirm: 'Confirmar y entregar',
    checkin_manual_label: 'ID de entrada (sin cámara)',
    checkin_manual_go: 'Buscar entrada',
    checkin_camera_denied: 'Cámara bloqueada. Abre este enlace en Safari o Chrome (no dentro de una app) o escribe el ID de la entrada arriba.',
    checkin_camera_missing: 'No hay cámara. Escribe el ID de la entrada arriba.',
    checkin_camera_failed: 'Cámara no disponible. Escribe el ID de la entrada arriba.',
    checkin_done: 'Entregado: {bands}',
    checkin_done_noband: 'Registrada',
    checkin_scanned: 'Registradas',
    checkin_bad_token: 'El enlace del escáner no es válido: pide uno nuevo.',
    checkin_at: 'Registrada',
    checkin_setup: 'Escáner de acceso',
    checkin_setup_hint: 'Abre este enlace en el móvil del personal de puerta. La lista de bandas y el enlace se crean al primer uso; «Nuevo enlace» revoca el anterior.',
    checkin_setup_counts: '{bands} bandas, {rules} reglas',
    checkin_rotate: 'Nuevo enlace',
    checkin_copy_link: 'Copiar enlace',
    door_link_title: 'Enlace de puerta (varios eventos)',
    door_link_create: 'Crear enlace de puerta',
    door_link_created: 'El enlace cubre {count} eventos',
    checkin_link_copied: 'Enlace del escáner copiado',
    checkin_edit_bands: 'Bandas y reglas',
    band_edit_title: 'Bandas y reglas',
    band_edit_hint:
      'Lo que se entrega en la puerta. Las reglas se resuelven al escanear, así que los cambios se aplican a las entradas ya vendidas.',
    band_loading: 'Cargando el esquema de bandas…',
    band_source_event: 'Bandas cargadas desde el registro del evento.',
    band_source_list:
      'No se pudo cargar el evento; se usa la lista de eventos.',
    band_types_inline: 'Los tipos de entrada venían en la respuesta.',
    band_types_endpoint:
      'Tipos de entrada cargados desde el endpoint de tipos.',
    band_section: 'Bandas',
    band_section_hint:
      'El id es fijo: las reglas apuntan a él, así que renombrar una banda nunca rompe una regla.',
    band_no_bands: 'Todavía no hay bandas.',
    band_add: 'Añadir banda',
    band_new_name: 'Nueva banda',
    band_col_name: 'Banda',
    band_col_label: 'Para quién es',
    band_col_colour: 'Color',
    band_id_caption: 'id {id} — fijo',
    band_delete: 'Eliminar banda',
    band_delete_blocked:
      '«{name}» todavía lo usan reglas ({count}). Quítalo de esas reglas primero.',
    band_in_use: 'Reglas que usan esta banda: {count}',
    band_rules_section: 'Reglas',
    band_rules_hint:
      'Se aplican todas las reglas que coincidan: se puede entregar una banda de acceso y una de rol. Las condiciones vacías no limitan.',
    band_no_rules: 'Todavía no hay reglas.',
    band_rule_n: 'Regla {n}',
    band_rule_bands: 'Bandas a entregar',
    band_rule_bands_hint: 'Todas las bandas que entrega esta regla.',
    band_rule_types: 'Tipos de entrada',
    band_rule_types_hint: 'Déjalo vacío para cualquier tipo de entrada.',
    band_rule_prefixes: 'Prefijos de código',
    band_rule_prefixes_hint: 'Separados por comas, p. ej. SPK-',
    band_rule_codes: 'Códigos exactos',
    band_rule_codes_hint: 'Separados por comas, p. ej. VOLUNTEER',
    band_rule_day: 'Día',
    band_rule_day_any: 'Cualquier día',
    band_rule_day_mon: 'Lunes',
    band_rule_day_tue: 'Martes',
    band_rule_day_wed: 'Miércoles',
    band_rule_day_thu: 'Jueves',
    band_rule_day_sun: 'Domingo',
    band_rule_day_fri: 'Viernes',
    band_rule_day_sat: 'Sábado',
    band_rule_per: 'Entregar',
    band_rule_per_ticket: 'Una por entrada',
    band_rule_per_redemption: 'Una por código',
    band_rule_add: 'Añadir regla',
    band_rule_delete: 'Eliminar regla',
    band_rule_condition_hint:
      'Una regla necesita al menos: tipo de entrada, prefijo de código o código exacto.',
    band_saved: 'Guardado: {bands} bandas, {rules} reglas',
    band_save_failed: 'No se pudo guardar el esquema de bandas.',
    band_load_failed: 'No se pudo cargar el esquema de bandas.',
    checkin_no_bands: 'Sin banda para esta entrada.',

    registered_success: 'Registrado',

    name_label: 'Nombre:',

    email_label: 'Email:',

    ticket_details: 'Detalles del ticket',

    yes: 'Sí',

    no: 'No',

    paid_label: 'Pagado:',

    id_label: 'ID:',

    failed: 'Fallido',

    ticket_id_label: 'ID de entrada:',

    error_label: 'Error:',

    ticket_heading: 'Entrada',

    ticket_instructions:
      '¡Guarda esta página como marcador, imprímela o toma una captura de pantalla y preséntala para registrarte!',

    ticket_paid: 'Pagado',

    ticket_not_paid: 'No pagado',

    ticket_deactivated: 'Desactivada',

    ticket_pending: 'Pendiente',

    deactivate_ticket: 'Desactivar entrada',

    activate_ticket: 'Activar entrada',

    checked_in: 'Registrado',

    not_checked_in: 'No registrado',

    print: 'Imprimir',

    ticket_types: 'Tipos de entrada',

    no_ticket_types: 'No hay tipos de entrada configurados.',

    no_ticket_types_available: 'No hay tipos de entrada disponibles para este evento.',

    available_until: 'Disponible hasta',

    tt_chip: '{name} - {price} {currency}',

    ticket_type_updated: 'Tipo de entrada actualizado.',

    ticket_type_added: 'Tipo de entrada añadido.',

    delete_ticket_type_confirm: '¿Está seguro de que quiere eliminar este tipo de entrada?',

    ticket_type_deleted: 'Tipo de entrada eliminado.',

    edit_ticket_type: 'Editar tipo de entrada',

    add_ticket_type: 'Añadir tipo de entrada',

    tt_name_label: 'Nombre',

    tt_description_label: 'Descripción',

    tt_image_url_label: 'URL de imagen',

    max_tickets_hint: 'Número máximo de entradas que se pueden vender (0 = ilimitado)',

    sort_order_label: 'Orden',

    available_from_label: 'Disponible desde',

    available_to_label: 'Disponible hasta',

    update_ticket_type: 'Actualizar tipo de entrada',

    save_ticket_type: 'Guardar tipo de entrada',

    promo_combinable: 'Combinable',

    promo_sec_identity: 'Identidad',

    promo_sec_effect: '¿Qué hace?',

    promo_sec_condition: '¿Cuándo se aplica?',

    promo_sec_limits: 'Límites y combinación',

    promo_sec_usage: 'Uso',

    promo_effect_discount: 'Descuento',

    promo_effect_grants: 'Añade entradas',

    promo_applies_to: 'Se aplica a',

    promo_applies_whole: 'toda la cesta',

    promo_applies_types: 'solo estos tipos de entrada',

    promo_sum_no_code: 'sin código',

    promo_sum_code: 'código {code}',

    promo_sum_any_buyer: 'cualquier comprador',

    promo_sum_requires: 'requiere {types}',

    promo_sum_any_ticket: 'cualquier entrada',

    promo_sum_grant: 'añade {qty} × {ticket} por persona',

    promo_sum_discount_percent: '{percent}% de descuento',

    promo_sum_discount_fixed: '{amount} {currency} de descuento',

    promo_sum_swap: 'anula la entrada presentada',

    promo_sum_uses: 'máx. {max}×',

    promo_sum_unlimited: 'canjes ilimitados',

    promo_ticket_type_scope: 'Limitar a tipos de entrada',

    promo_ticket_type_scope_hint: 'Opcional: restringe este código a tipos de entrada concretos. Déjalo vacío para aplicarlo a toda la cesta.',

    promo_ticket_type_scope_all: 'Todos los tipos de entrada',

    promo_max_total_tickets: 'Entradas máximas',
    promo_max_total_tickets_hint:
      'Tope estricto en todos los pedidos: como máximo estas entradas en total, sean los pedidos que sean. Vacío = sin tope.',
    promo_max_uses: 'Pedidos (usos)',

    promo_max_uses_hint:
      'Pedidos distintos que pueden usar este código en total (0 = ilimitado). Límite real = entradas por pedido x esto.',


    promo_cap_total:
      'Hasta {total} entradas en total ({per} por pedido x {uses} pedido(s)).',

    promo_cap_no_per_order:
      'Cualquier número por pedido, hasta {uses} pedido(s) en total.',

    promo_cap_no_order_limit:
      'Sin límite global: hasta {per} por pedido.',

    promo_cap_unlimited:
      'Sin límites: cualquier número por pedido, pedidos ilimitados.',
    promo_cap_global:
      'Tope estricto: {total} entradas en total.',
    promo_uses_label: 'Usos: {used} / {max}',

    promo_uses_unlimited: 'Usado: {used} veces (ilimitado)',

    promo_require_ticket: 'Requiere un ID de entrada',

    promo_require_ticket_hint: 'El comprador debe ingresar un ID de entrada existente además del código. Úsalo para mejoras ("cambiar mi entrada") y ofertas de entradas adicionales ("trae un amigo a mitad de precio").',

    promo_grants_toggle: 'Añade entradas en lugar de un descuento',

    promo_grants_ticket_type: 'Entrada que añadir',

    promo_grants_per_source: 'Entradas por persona',

    promo_grants_per_source_hint:
      'Se multiplica por las personas que cubre la entrada presentada ("admits" del tipo de entrada).',

    promo_grants_hint:
      'No se aplica descuento: se añade la entrada anterior, {per} por persona cubierta por la entrada presentada.',

    promo_title_label: 'Nombre de la oferta',

    promo_title_hint:
      'Opcional. Se muestra en la lista de promociones, para que una oferta sin código siga siendo identificable.',

    admits_label: 'Admite (personas)',

    admits_hint:
      'Cuántas personas cubre una entrada de este tipo. Una entrada familiar que admite 4 desbloquea cuatro añadidos.',

    cap_group_label: 'Grupo de límite compartido',

    cap_group_hint:
      'Opcional. Los tipos que comparten grupo comparten UN límite entre eventos (p. ej. un cupo de asientos).',

    promo_code_optional_hint: 'Opcional: déjalo vacío y cualquier ID de entrada válido activa esta oferta.',

    promo_code_required_hint: 'El comprador escribe este código al pagar.',

    promo_redemptions_per_ticket: 'Canjes por entrada',

    promo_redemptions_per_ticket_hint: 'Cuántas compras puede descontar este ID de entrada (predeterminado 1 = un solo uso)',

    promo_max_tickets: 'Entradas por pedido',

    promo_max_tickets_hint:
      'Entradas en UN pedido a las que se aplica este código; las demás no quedan cubiertas. Vacío = sin límite por pedido.',

    promo_ticket_code_hint: 'Los compradores canjean ingresando un ID de entrada válido junto con el código de la oferta',

    promo_source_events: 'Eventos de origen',

    promo_source_events_hint: 'De qué eventos puede provenir la entrada de origen. Déjalo vacío para solo este evento; añade otros para permitir mejoras entre eventos.',

    promo_source_ticket_types: 'Tipos de entrada de origen',

    promo_source_ticket_types_hint: 'Opcional: restringe qué tipos de entrada pueden usarse como origen, p. ej. solo entradas Early Bird.',

    promo_source_move: 'Cambiar mi entrada',

    promo_source_move_hint: 'Anula la entrada de origen y libera su plaza cuando se pague esta compra: es una mejora, no una entrada adicional.',

    promo_source_credit: 'Crédito de origen',

    promo_source_credit_none: 'Sin crédito',

    promo_source_credit_paid: 'Acreditar lo pagado',

    promo_source_credit_hint: 'El crédito añade lo que realmente costó la entrada de origen, así el comprador solo paga la diferencia. Añade un descuento encima para incentivar más la mejora. Limitado al precio de la nueva entrada.',

    discount_type: 'Tipo de descuento',

    discount_percent_label: '% Descuento',

    discount_fixed_label: 'Descuento fijo',

    bulk_actions: 'Acciones masivas',

    resend_all_emails: 'Reenviar todos los emails de entradas',

    email_all_attendees: 'Enviar email a todos los asistentes',

    email_all_attendees_title: 'Enviar email a todos los asistentes',

    email_subject_label: 'Asunto',

    email_message_label: 'Mensaje',

    send: 'Enviar',

    admin_email_label: 'Email del administrador',

    admin_email_hint: 'Recibir notificaciones por email de ventas de entradas',

    bulk_email_sent: 'Emails de entradas reenviados.',

    confirm_resend_all: '¿Está seguro de que quiere reenviar todos los emails de entradas para este evento?',

    bulk_message_sent: 'Mensaje enviado a todos los asistentes.',

    quantity: 'Cantidad',

    add_to_basket: 'Añadir a la cesta',

    basket_summary_one: '{count} entrada · {total}',

    basket_summary_many: '{count} entradas · {total}',

    ticket_added_to_basket: '{qty} × {name} añadido a tu cesta',

    ticket_removed_from_basket: '{name} eliminado de tu cesta',

    view_basket: 'Ver cesta',

    anon_dialog_title: '¿Modo incógnito?',

    anon_dialog_body:
      'Entrada anónima: sin nombre ni email no podemos reenviarte la entrada ni enviarte novedades del evento — así que cuida ese enlace como una seed phrase. Si lo pierdes, no tenemos forma de mandarte otro.',

    anon_dialog_confirm: 'Anónimo total',

    anon_dialog_back: 'Añadir mis datos',

    copy_details_to_all: 'Copiar a todos',

    attendee: 'Asistente',

    attendees_for: 'Asistentes para',

    name: 'Nombre',

    basket: 'Cesta',

    promo_code_comma_separated: 'Código promocional o ID de entrada (separados por comas)',

    promo_pending_ticket_id_only:
      'Esta entrada necesita una entrada existente: introduce tu ID de entrada en el campo de código promocional de arriba.',

    promo_pending_ticket:
      '{code} también necesita tu ID de entrada existente: añádelo en la misma casilla de Promo Code, separado por una coma.',

    promo_grant_confirmed:
      'ID de entrada aceptado: {quantity} × {name} desbloqueado. Pulsa Pagar para reclamarlo.',

    promo_none_found: 'No se encontraron códigos promocionales válidos',

    promo_reason_generic: 'Este código no se pudo usar.',

    promo_reason_ticket_not_found: 'No es un código de oferta ni un ID de entrada reconocido.',

    promo_reason_ticket_id_not_found:
      'No se encontró ese ID de entrada. No lleva espacios, así que comprueba que lo copiaste entero — o usa el botón «Copiar ID de entrada» de tu entrada.',

    promo_reason_ticket_not_eligible: 'Esa entrada no es válida para esta oferta.',

    promo_reason_ticket_out_of_scope: 'Esa entrada no pertenece a un evento o tipo de entrada válido.',

    promo_reason_ticket_already_used: 'Esa entrada ya se usó para una oferta.',

    promo_reason_ticket_redemptions_exhausted: 'Esa entrada ya ha agotado todos sus canjes para esta oferta.',

    promo_reason_promo_uses_exhausted: 'Esta oferta ha alcanzado su límite de uso.',
    promo_reason_promo_tickets_exhausted:
      'Esta oferta ya no tiene entradas disponibles.',

    promo_reason_ticket_needs_offer_code:
      'Introduce el código de oferta además de tu ID de entrada, ambos en la casilla de Promo Code.',

    promo_reason_ticket_count_not_eligible: 'Esta oferta no cubre el número de entradas de tu cesta.',

    promo_reason_ticket_not_applicable: 'Ese ID de entrada no se puede usar con los códigos introducidos.',

    promo_reason_currency_mismatch: 'Esa entrada está en otra moneda y no se puede acreditar.',

    promo_code_hint: 'Introduce códigos promocionales separados por comas',

    checkout: 'Pagar',

    apply: 'Aplicar',

        loading: 'Loading...',

    basket_not_found: 'Cesta no encontrada.',

    basket_confirmed: '¡Pago confirmado! Sus entradas están listas.',

    basket_pending: 'Esperando confirmación de pago...',

    buyer: 'Comprador',

    your_tickets: 'Sus Entradas',

    buy_more: 'Comprar más entradas',

    anon: 'Anónimo',

    col_ticket_type: 'Tipo de entrada',

    ticket_count_one: '1 entrada',

    ticket_count_many: '{count} entradas',

    show_ticket: 'Mostrar entrada',

    copy_url: 'Copiar enlace',

    ticket_id_label: 'ID de entrada',

    copy_ticket_id: 'Copiar ID de entrada',

    copy_ticket_id_done: 'ID de entrada copiado',

    continue_payment: 'Continuar con el pago',

    basket_auto_update: 'Cesta actualizándose...',

    total: 'Total',
  }
})
