from ..models import PackageDay


def _sync_package_itinerary_json(package):
    package_days = package.package_days.prefetch_related('options').all()
    package.itinerary = [
        {
            'day': package_day.day_number,
            'title': package_day.title,
            'activity_type': 'travel',
            'description': package_day.description,
            'inclusions': ', '.join(option.title for option in package_day.options.all()),
        }
        for package_day in package_days
    ]
    package.save(update_fields=['itinerary', 'updated_at'])


def _build_selected_options_summary(selected_options):
    return [
        {
            'day_number': package_day.day_number,
            'day_title': package_day.title,
            'option_title': selected_option.title,
            'option_type': selected_option.get_option_type_display(),
            'additional_cost': selected_option.additional_cost,
            'description': selected_option.description,
        }
        for package_day, selected_option in selected_options
    ]


def _build_action_button_label(option):
    if not option.action_link:
        return None
    if option.option_type == 'flight':
        return 'Book Flight'

    title = (option.title or '').strip()
    if title and len(title) <= 30:
        return f'Open {title}'
    return 'Open Link'


def _build_group_title(items, action_link):
    if not items:
        return 'Selections'

    if action_link:
        option_type_keys = {item['option_type_key'] for item in items}
        if option_type_keys == {'flight'}:
            return 'Flights'
        if option_type_keys == {'stay'}:
            return 'Stays'
        if option_type_keys == {'activity'}:
            return 'Activities'
        if len(items) > 1:
            return 'Shared Actions'

    if len(items) == 1:
        return f"Day {items[0]['day_number']}"
    return 'Selections'


def _build_booking_selection_items(custom_itinerary):
    if not custom_itinerary:
        return []

    selections = (
        custom_itinerary.selections.select_related('package_day', 'selected_option')
        .all()
        .order_by('package_day__day_number', 'package_day__sort_order', 'id')
    )

    return [
        {
            'day_number': selection.package_day.day_number,
            'day_title': selection.package_day.title,
            'day_description': selection.package_day.description,
            'option_title': selection.selected_option.title,
            'option_type_key': selection.selected_option.option_type,
            'option_type': selection.selected_option.get_option_type_display(),
            'option_description': selection.selected_option.description,
            'selected_price': selection.selected_price,
            'action_link': selection.selected_option.action_link,
            'action_button_label': _build_action_button_label(selection.selected_option),
        }
        for selection in selections
    ]


def _group_booking_selection_items(selection_items):
    groups = []
    index_by_link = {}

    for item in selection_items:
        action_link = item['action_link']
        if action_link:
            group_index = index_by_link.get(action_link)
            if group_index is None:
                groups.append({
                    'group_key': action_link,
                    'group_link': action_link,
                    'group_button_label': item['action_button_label'] or 'Open Link',
                    'items': [],
                })
                index_by_link[action_link] = len(groups) - 1
                group_index = index_by_link[action_link]
            groups[group_index]['items'].append(item)
        else:
            groups.append({
                'group_key': f"ungrouped-{len(groups)}",
                'group_link': None,
                'group_button_label': None,
                'items': [item],
            })

    for group in groups:
        group['group_title'] = _build_group_title(group['items'], group['group_link'])

    return groups

