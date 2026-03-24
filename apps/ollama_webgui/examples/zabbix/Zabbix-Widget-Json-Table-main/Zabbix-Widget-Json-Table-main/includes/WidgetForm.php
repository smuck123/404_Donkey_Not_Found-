<?php

namespace Modules\JsonTableWidget\Includes;

use Zabbix\Widgets\CWidgetForm;
use Zabbix\Widgets\CWidgetField;
use Zabbix\Widgets\Fields\CWidgetFieldMultiSelectItem;
use Zabbix\Widgets\Fields\CWidgetFieldCheckBox;
use Zabbix\Widgets\Fields\CWidgetFieldSelect;
use Zabbix\Widgets\Fields\CWidgetFieldTextBox;

class WidgetForm extends CWidgetForm {

	private const CHART_TYPE_OPTIONS = [
		0 => 'Bar',
		1 => 'Compact bar',
		2 => 'Stacked bar',
		3 => 'Dot',
		4 => 'Value only',
		5 => 'Line',
		6 => 'Lollipop',
		7 => 'Soft area'
	];

	private const COLOR_OPTIONS = [
		0 => 'Green',
		1 => 'Amber',
		2 => 'Red',
		3 => 'Blue',
		4 => 'Violet',
		5 => 'Cyan',
		6 => 'Teal',
		7 => 'Orange',
		8 => 'Pink',
		9 => 'Gray',
		10 => 'Slate',
		11 => 'Indigo',
		12 => 'Lime',
		13 => 'Brown',
		14 => 'Black'
	];

	private const COLOR_THEME_OPTIONS = [
		0 => 'Ocean',
		1 => 'Violet',
		2 => 'Forest',
		3 => 'Sunset',
		4 => 'Fire',
		5 => 'Ice',
		6 => 'Mono',
		7 => 'Neon',
		8 => 'Pastel',
		9 => 'Earth'
	];

	public function addFields(): self {
		return $this
			->addField(
				(new CWidgetFieldMultiSelectItem('itemid', _('Item')))
					->setFlags(CWidgetField::FLAG_NOT_EMPTY | CWidgetField::FLAG_LABEL_ASTERISK)
					->setMultiple(false)
			)
			->addField((new CWidgetFieldCheckBox('show_summary', _('Show summary counters')))->setDefault(1))
			->addField((new CWidgetFieldCheckBox('show_expand', _('Show nested detail rows')))->setDefault(1))
			->addField((new CWidgetFieldCheckBox('show_chart', _('Show chart')))->setDefault(0))
			->addField((new CWidgetFieldCheckBox('dark_header', _('Dark table header')))->setDefault(1))
			->addField((new CWidgetFieldCheckBox('compact_mode', _('Compact mode')))->setDefault(0))
			->addField(new CWidgetFieldTextBox('visible_columns', _('Visible table columns (comma-separated)')))
			->addField(new CWidgetFieldTextBox('chart_label_column', _('Chart label column')))
			->addField(new CWidgetFieldTextBox('chart_value_columns', _('Chart value columns (comma-separated)')))
			->addField((new CWidgetFieldSelect('chart_type', _('Chart type'), self::CHART_TYPE_OPTIONS))->setDefault(0))
			->addField((new CWidgetFieldCheckBox('show_second_chart', _('Show second chart panel')))->setDefault(0))
			->addField(new CWidgetFieldTextBox('chart2_label_column', _('Second chart label column')))
			->addField(new CWidgetFieldTextBox('chart2_value_columns', _('Second chart value columns (comma-separated)')))
			->addField((new CWidgetFieldSelect('chart2_type', _('Second chart type'), self::CHART_TYPE_OPTIONS))->setDefault(0))
			->addField((new CWidgetFieldTextBox('max_chart_rows', _('Max chart rows')))->setDefault('10'))
			->addField((new CWidgetFieldSelect('color_theme', _('Color theme'), self::COLOR_THEME_OPTIONS))->setDefault(0))
			->addField((new CWidgetFieldTextBox('chart_palette', _('Chart palette override (#hex,#hex,...)')))->setDefault(''))
			->addField((new CWidgetFieldSelect('color_ok', _('OK color'), self::COLOR_OPTIONS))->setDefault(0))
			->addField((new CWidgetFieldSelect('color_warn', _('Warn color'), self::COLOR_OPTIONS))->setDefault(1))
			->addField((new CWidgetFieldSelect('color_error', _('Error color'), self::COLOR_OPTIONS))->setDefault(2))
			->addField((new CWidgetFieldSelect('color_info', _('Info color'), self::COLOR_OPTIONS))->setDefault(3))
			->addField(new CWidgetFieldTextBox('status_color_map', _('Status color map (VALUE=#hex,VALUE=#hex)')));
	}
}
