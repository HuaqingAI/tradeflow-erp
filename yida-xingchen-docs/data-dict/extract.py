"""
Extract data dictionary from YiDa ERP form schemas.
Outputs one Markdown file per module group under data-dictionary/.
"""
import os
import json
from collections import defaultdict

FORMS_DIR = os.path.join(os.path.dirname(__file__), '../../uploads/yida-xingchen-formschema/forms')
NAV_JSON  = os.path.join(os.path.dirname(__file__), '../../uploads/yida-xingchen-formschema/nav.json')
OUT_DIR   = os.path.dirname(__file__)

# ── Component type → human-readable field type ──────────────────────────────
FIELD_TYPE_MAP = {
    'TextField':            '文本',
    'TextareaField':        '多行文本',
    'NumberField':          '数字',
    'SelectField':          '下拉单选',
    'MultiSelectField':     '下拉多选',
    'RadioField':           '单选',
    'CheckboxField':        '多选',
    'DateField':            '日期',
    'CascadeDateField':     '级联日期',
    'ImageField':           '图片',
    'AttachmentField':      '附件',
    'EmployeeField':        '人员',
    'DepartmentSelectField':'部门',
    'AssociationFormField': '关联表单',
    'AssociationQuery':     '关联查询',
    'SerialNumberField':    '流水号',
    'AddressField':         '地址',
    'CascadeSelectField':   '级联选择',
    'CountrySelectField':   '国家/地区',
    'EditorField':          '富文本',
    'RateField':            '评分',
    'TableField':           '子表格',
    'PageSection':          '分组',
    'ColumnsLayout':        '多列布局',
    'Column':               '列',
    'TabsLayout':           'Tab布局',
    'Tab':                  'Tab页',
    'FormContainer':        '表单容器',
}

# Components that are layout/structural (not fields but may contain fields)
LAYOUT_COMPONENTS = {'ColumnsLayout', 'Column', 'PageSection', 'FormContainer',
                     'TabsLayout', 'Tab', 'RootContent', 'RootHeader', 'RootFooter',
                     'Div', 'PageHeader', 'PageHeaderContent', 'PageHeaderTab', 'FooterYida'}

# Components to skip entirely (UI / report widgets, not data fields)
SKIP_COMPONENTS = {
    'Button', 'Link', 'Text', 'Image', 'Video', 'RichText', 'Drawer',
    'DataCard', 'Tree', 'Filter2', 'TablePc', 'CC_PortalCarouselView',
    'CC_PortalQuickEntryView', 'CC_PortalTodoIndicatorView', 'CC_PG_ESignField',
    'YoushuCrossPivotTable', 'YoushuGroupedBarChart', 'YoushuInputFilter',
    'YoushuLineChart', 'YoushuMap', 'YoushuPieChart', 'YoushuSelectFilter',
    'YoushuSimpleIndicatorCard', 'YoushuTable', 'YoushuTimeFilter',
    'YoushuTopFilterContainer', 'YoushuPageHeader',
}


def get_zh(value):
    """Extract Chinese text from i18n value or return string."""
    if isinstance(value, dict):
        return value.get('zh_CN') or value.get('en_US') or ''
    return str(value) if value else ''


def get_options(props):
    """Extract select options list as string."""
    options = props.get('options') or props.get('dataSource') or []
    if not isinstance(options, list):
        return ''
    labels = []
    for opt in options:
        if isinstance(opt, dict):
            label = get_zh(opt.get('label', opt.get('text', opt.get('value', ''))))
            if label:
                labels.append(label)
    return '、'.join(labels) if labels else ''


def extract_fields(nodes, parent_section='', depth=0, results=None):
    """Recursively walk component tree and extract field rows."""
    if results is None:
        results = []

    for node in nodes:
        cname = node.get('componentName', '')
        props  = node.get('props', {})
        children = node.get('children', [])

        if cname in SKIP_COMPONENTS:
            continue

        if cname == 'TableField':
            # Sub-table: label it as a section, then extract its columns
            label = get_zh(props.get('label', props.get('title', '')))
            field_id = props.get('fieldId', node.get('id', ''))
            required = 'Y' if props.get('required') else ''
            hidden = 'Y' if props.get('hidden') else ''
            results.append({
                'section': parent_section,
                'field_id': field_id,
                'label': label,
                'type': '子表格',
                'required': required,
                'hidden': hidden,
                'options': '',
                'remark': '',
                'is_subtable_header': True,
            })
            # Process sub-table columns
            sub_section = label or '子表格'
            extract_fields(children, parent_section=sub_section, depth=depth+1, results=results)
            continue

        if cname == 'PageSection':
            label = get_zh(props.get('label', props.get('title', '')))
            # Don't emit a row for hidden sections named "隐藏分组"
            # but still walk children (they may have real fields)
            section_name = label if label and label != '隐藏分组' else parent_section
            if label and label != '隐藏分组':
                results.append({
                    'section': parent_section,
                    'field_id': '',
                    'label': f'【{label}】',
                    'type': '分组',
                    'required': '',
                    'hidden': '',
                    'options': '',
                    'remark': '',
                    'is_section': True,
                })
            extract_fields(children, parent_section=section_name, depth=depth, results=results)
            continue

        if cname in LAYOUT_COMPONENTS:
            extract_fields(children, parent_section=parent_section, depth=depth, results=results)
            continue

        # It's a real field component
        label    = get_zh(props.get('label', props.get('title', props.get('placeholder', ''))))
        field_id = props.get('fieldId', node.get('id', ''))
        required = 'Y' if props.get('required') else ''
        hidden   = 'Y' if props.get('hidden') else ''
        ftype    = FIELD_TYPE_MAP.get(cname, cname)
        options  = get_options(props)

        if not label:
            # Walk children for nested content even in unknown components
            extract_fields(children, parent_section=parent_section, depth=depth, results=results)
            continue

        results.append({
            'section': parent_section,
            'field_id': field_id,
            'label': label,
            'type': ftype,
            'required': required,
            'hidden': hidden,
            'options': options,
            'remark': '',
        })

        if children:
            extract_fields(children, parent_section=parent_section, depth=depth+1, results=results)

    return results


def load_form_fields(form_uuid):
    """Find the form directory and extract its fields."""
    for d in os.listdir(FORMS_DIR):
        if form_uuid in d:
            schema_path = os.path.join(FORMS_DIR, d, 'schema.json')
            if not os.path.exists(schema_path):
                return []
            with open(schema_path, encoding='utf-8') as f:
                schema = json.load(f)
            pages = schema.get('pages', [])
            if not pages:
                return []
            fields = []
            for page in pages:
                for root in page.get('componentsTree', []):
                    for child in root.get('children', []):
                        extract_fields([child], results=fields)
            return fields
    return []


def build_nav_tree():
    with open(NAV_JSON, encoding='utf-8') as f:
        data = json.load(f)
    items = data['content']

    recycle_uuids = {
        'NAV-3L766Y81CB6M0O7W7C5V48EACWG62T3GN4OXLC',
        'NAV-AWC66LB1IE41KF1VKNTU9B6QICTE2VTTGSQIMQ',
    }

    def collect_all_under(parent_uuids):
        all_under = set(parent_uuids)
        queue = list(parent_uuids)
        while queue:
            parent = queue.pop()
            for item in items:
                if item.get('parentNavUuid') == parent:
                    uid = item['navUuid']
                    if uid not in all_under:
                        all_under.add(uid)
                        queue.append(uid)
        return all_under

    recycle_all = collect_all_under(recycle_uuids)

    children_map = defaultdict(list)
    for item in items:
        if item['navUuid'] in recycle_all:
            continue
        parent = item.get('parentNavUuid', '')
        children_map[parent].append(item)

    # Sort children by listOrder
    for k in children_map:
        children_map[k].sort(key=lambda x: x.get('listOrder', 0))

    return children_map


def render_fields_md(fields):
    """Render field list as Markdown table rows."""
    lines = []
    lines.append('| 字段名称 | 字段ID | 字段类型 | 必填 | 备注/选项值 |')
    lines.append('|---------|--------|--------|------|------------|')
    for f in fields:
        if f.get('is_section'):
            lines.append(f'| **{f["label"]}** |  |  |  |  |')
            continue
        if f.get('is_subtable_header'):
            lines.append(f'| **▼ {f["label"]}（子表格）** | `{f["field_id"]}` | 子表格 | {f["required"]} |  |')
            continue
        hidden_note = '（隐藏）' if f.get('hidden') else ''
        options = f.get('options', '')
        remark = f'{hidden_note}{options}'.strip()
        lines.append(f'| {f["label"]} | `{f["field_id"]}` | {f["type"]} | {f["required"]} | {remark} |')
    return '\n'.join(lines)


def generate_module_md(module_title, pages, children_map):
    """Generate Markdown for one nav module."""
    lines = [f'# {module_title}\n']

    for page in pages:
        form_uuid = page.get('formUuid') or ''
        page_title = get_zh(page.get('title') or page.get('i18nTitle') or {})

        if not form_uuid or form_uuid.startswith('REPORT-') or form_uuid.startswith('NAV-SYSTEM-'):
            continue

        lines.append(f'\n## {page_title}\n')
        lines.append(f'**表单ID:** `{form_uuid}`\n')

        fields = load_form_fields(form_uuid)
        if not fields:
            lines.append('_（无可提取字段或为门户页面）_\n')
            continue

        # Filter to non-empty fields
        real_fields = [f for f in fields if f.get('label')]
        if not real_fields:
            lines.append('_（无字段）_\n')
            continue

        lines.append(render_fields_md(real_fields))
        lines.append('')

    return '\n'.join(lines)


def main():
    children_map = build_nav_tree()

    # Top-level modules (parent = NAV-SYSTEM-PARENT-UUID)
    top_items = children_map.get('NAV-SYSTEM-PARENT-UUID', [])

    # Build index
    index_lines = ['# TradeFlow ERP 数据字典索引\n',
                   '本目录由宜搭表单 schema 自动提取，包含各模块表单的字段定义。\n',
                   '## 模块列表\n']

    module_files = []

    for top in top_items:
        nav_type = top.get('navType', '')
        title = get_zh(top.get('title') or top.get('i18nTitle') or {})
        nav_uuid = top['navUuid']

        # Skip system nav items
        if nav_type == 'SYSTEM':
            continue

        if nav_type == 'NAV':
            # Module group — collect child pages
            child_pages = children_map.get(nav_uuid, [])
            if not child_pages:
                continue
            slug = title.replace('/', '_').replace(' ', '_')
            filename = f'{slug}.md'
            md = generate_module_md(title, child_pages, children_map)
            out_path = os.path.join(OUT_DIR, filename)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(md)
            module_files.append((title, filename))
            print(f'  Written: {filename}')
        elif nav_type == 'PAGE':
            # Top-level page (not inside a group)
            form_uuid = top.get('formUuid') or ''
            if not form_uuid or form_uuid.startswith('REPORT-'):
                continue
            # Collect standalone pages into a misc file
            module_files.append((title, None, top))

    # Write standalone pages into a "其他页面.md"
    standalone = [(t, p) for t, fn, *rest in [(x[0], x[1], x[2] if len(x) > 2 else None) for x in module_files] if fn is None and rest[0] for t, p in [(t, rest[0])]]
    module_files_clean = [(t, fn) for t, fn, *_ in [(x[0], x[1]) for x in module_files] if fn is not None]

    if standalone:
        lines = ['# 独立页面\n']
        for title, page in standalone:
            form_uuid = page.get('formUuid') or ''
            lines.append(f'\n## {title}\n')
            lines.append(f'**表单ID:** `{form_uuid}`\n')
            fields = load_form_fields(form_uuid)
            real_fields = [f for f in fields if f.get('label')]
            if real_fields:
                lines.append(render_fields_md(real_fields))
            else:
                lines.append('_（无可提取字段）_')
            lines.append('')
        out_path = os.path.join(OUT_DIR, '独立页面.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        module_files_clean.append(('独立页面', '独立页面.md'))
        print('  Written: 独立页面.md')

    # Write index
    for title, filename in module_files_clean:
        index_lines.append(f'- [{title}]({filename})')
    index_lines.append('')

    with open(os.path.join(OUT_DIR, 'README.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(index_lines))
    print('  Written: README.md')


if __name__ == '__main__':
    main()
