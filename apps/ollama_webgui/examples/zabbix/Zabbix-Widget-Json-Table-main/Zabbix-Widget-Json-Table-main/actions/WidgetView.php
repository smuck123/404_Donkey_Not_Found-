<?php

namespace Modules\JsonTableWidget\Actions;

use CControllerDashboardWidgetView;
use CControllerResponseData;

class WidgetView extends CControllerDashboardWidgetView {

	private const CHART_TYPES = [
		0 => 'bar',
		1 => 'compact-bar',
		2 => 'stacked-bar',
		3 => 'dot',
		4 => 'value-only',
		5 => 'line',
		6 => 'lollipop',
		7 => 'soft-area'
	];


	private const NAMED_COLORS = [
		0 => '#22c55e',
		1 => '#f59e0b',
		2 => '#ef4444',
		3 => '#3b82f6',
		4 => '#8b5cf6',
		5 => '#06b6d4',
		6 => '#14b8a6',
		7 => '#f97316',
		8 => '#ec4899',
		9 => '#6b7280',
		10 => '#475569',
		11 => '#6366f1',
		12 => '#84cc16',
		13 => '#92400e',
		14 => '#111827'
	];

	private const COLOR_THEMES = [
		0 => 'ocean',
		1 => 'violet',
		2 => 'forest',
		3 => 'sunset',
		4 => 'fire',
		5 => 'ice',
		6 => 'mono',
		7 => 'neon',
		8 => 'pastel',
		9 => 'earth'
	];

	private function isListArray($value): bool {
		if (!is_array($value)) {
			return false;
		}

		return array_keys($value) === range(0, count($value) - 1);
	}

	private function parseCsv(string $value): array {
		$result = [];
		foreach (explode(',', $value) as $part) {
			$part = trim($part);
			if ($part !== '') {
				$result[] = $part;
			}
		}
		return array_values(array_unique($result));
	}

	private function normalizeRows($decoded): array {
		$rows = [];

		if (is_array($decoded)) {
			if ($this->isListArray($decoded)) {
				foreach ($decoded as $entry) {
					if (is_array($entry)) {
						$rows[] = $entry;
					}
					else {
						$rows[] = ['value' => $entry];
					}
				}
			}
			else {
				$rows[] = $decoded;
			}
		}
		else {
			$rows[] = ['value' => $decoded];
		}

		return $rows;
	}

	private function getColumns(array $rows): array {
		$columns = [];

		foreach ($rows as $row) {
			foreach (array_keys($row) as $key) {
				if (!in_array($key, $columns, true)) {
					$columns[] = $key;
				}
			}
		}

		return $columns;
	}

	private function detectSummary(array $decoded): array {
		if (isset($decoded['summary']) && is_array($decoded['summary'])) {
			return $decoded['summary'];
		}

		$summary = [];
		foreach ($decoded as $k => $v) {
			if (!is_array($v) && !is_object($v)) {
				$summary[$k] = $v;
			}
		}
		return $summary;
	}

	private function detectRows($decoded): array {
		if (is_array($decoded) && !$this->isListArray($decoded)) {
			$candidates = ['rows', 'data', 'failedRuns', 'flows', 'latestFailedActivities', 'tables'];

			foreach ($candidates as $candidate) {
				if (isset($decoded[$candidate])) {
					return $this->normalizeRows($decoded[$candidate]);
				}
			}

			foreach ($decoded as $v) {
				if ($this->isListArray($v)) {
					return $this->normalizeRows($v);
				}
			}
		}

		return $this->normalizeRows($decoded);
	}

	private function resolveColumnName(array $columns, string $name): ?string {
		$name_lc = strtolower($name);

		foreach ($columns as $column) {
			if (strtolower($column) === $name_lc) {
				return $column;
			}
		}

		return null;
	}

	private function resolveColumnNames(array $columns, array $names): array {
		$result = [];

		foreach ($names as $name) {
			$resolved = $this->resolveColumnName($columns, $name);
			if ($resolved !== null && !in_array($resolved, $result, true)) {
				$result[] = $resolved;
			}
		}

		return $result;
	}

	private function detectStatusColumns(array $columns): array {
		$preferred = ['status', 'state', 'action', 'severity', 'level'];

		return $this->resolveColumnNames($columns, $preferred);
	}

	private function detectChartColumns(array $rows, array $columns): array {
		$label_column = '';
		$value_columns = [];

		$preferred_label = ['name', 'hostname', 'pipelinename', 'flow', 'srcip', 'dstip', 'service', 'owner'];
		foreach ($preferred_label as $p) {
			$resolved = $this->resolveColumnName($columns, $p);
			if ($resolved !== null) {
				$label_column = $resolved;
				break;
			}
		}

		if ($label_column === '') {
			foreach ($columns as $col) {
				foreach ($rows as $row) {
					if (isset($row[$col]) && !is_array($row[$col]) && !is_object($row[$col]) && !is_numeric($row[$col])) {
						$label_column = $col;
						break 2;
					}
				}
			}
		}

		$preferred_numeric = ['runs', 'count', 'days_left', 'cpu_pct', 'memory_pct', 'requests', 'total_bytes', 'sent_bytes', 'rcvd_bytes', 'duration_sec', 'value'];
		$value_columns = $this->resolveColumnNames($columns, $preferred_numeric);

		if (!$value_columns) {
			foreach ($columns as $col) {
				foreach ($rows as $row) {
					if (isset($row[$col]) && !is_array($row[$col]) && !is_object($row[$col]) && is_numeric($row[$col])) {
						$value_columns[] = $col;
						break;
					}
				}
			}
		}

		return [
			'label' => $label_column,
			'values' => array_values(array_unique($value_columns))
		];
	}

	private function sanitizeColor(string $color, string $fallback): string {
		$color = trim($color);

		if ($color === '') {
			return $fallback;
		}

		if (preg_match('/^#[0-9a-fA-F]{6}$/', $color) || preg_match('/^#[0-9a-fA-F]{3}$/', $color)) {
			return $color;
		}

		return $fallback;
	}

	private function resolveNamedColor($value, string $fallback): string {
		if (is_numeric($value)) {
			$index = (int) $value;
			if (array_key_exists($index, self::NAMED_COLORS)) {
				return self::NAMED_COLORS[$index];
			}
		}

		$value = trim((string) $value);
		if (preg_match('/^#[0-9a-fA-F]{6}$/', $value) || preg_match('/^#[0-9a-fA-F]{3}$/', $value)) {
			return $value;
		}

		return $fallback;
	}

	private function getColorThemes(): array {
		return [
			'ocean' => ['#0284c7', '#0ea5e9', '#06b6d4', '#14b8a6', '#2563eb', '#0891b2'],
			'violet' => ['#7c3aed', '#8b5cf6', '#6366f1', '#a855f7', '#9333ea', '#6d28d9'],
			'forest' => ['#166534', '#16a34a', '#22c55e', '#15803d', '#65a30d', '#4d7c0f'],
			'sunset' => ['#ea580c', '#f97316', '#fb7185', '#f43f5e', '#f59e0b', '#ef4444'],
			'fire' => ['#b91c1c', '#dc2626', '#ef4444', '#f97316', '#ea580c', '#f59e0b'],
			'ice' => ['#0f766e', '#0891b2', '#06b6d4', '#67e8f9', '#38bdf8', '#0284c7'],
			'mono' => ['#374151', '#4b5563', '#6b7280', '#9ca3af', '#111827', '#334155'],
			'neon' => ['#d946ef', '#22d3ee', '#84cc16', '#f97316', '#f43f5e', '#a3e635'],
			'pastel' => ['#93c5fd', '#c4b5fd', '#86efac', '#f9a8d4', '#fdba74', '#67e8f9'],
			'earth' => ['#92400e', '#b45309', '#a16207', '#4d7c0f', '#57534e', '#854d0e']
		];
	}

	private function resolveChartType($value): string {
		if (is_numeric($value)) {
			$index = (int) $value;
			if (array_key_exists($index, self::CHART_TYPES)) {
				return self::CHART_TYPES[$index];
			}
		}

		$value = trim((string) $value);
		if (in_array($value, self::CHART_TYPES, true)) {
			return $value;
		}

		return 'bar';
	}

	private function resolveColorTheme($value): string {
		if (is_numeric($value)) {
			$index = (int) $value;
			if (array_key_exists($index, self::COLOR_THEMES)) {
				return self::COLOR_THEMES[$index];
			}
		}

		$value = strtolower(trim((string) $value));
		if (in_array($value, self::COLOR_THEMES, true)) {
			return $value;
		}

		return 'ocean';
	}

	protected function doAction(): void {
		$itemids = $this->fields_values['itemid'] ?? [];
		$show_summary = (int) ($this->fields_values['show_summary'] ?? 1);
		$show_expand = (int) ($this->fields_values['show_expand'] ?? 1);
		$show_chart = (int) ($this->fields_values['show_chart'] ?? 0);
		$dark_header = (int) ($this->fields_values['dark_header'] ?? 1);
		$compact_mode = (int) ($this->fields_values['compact_mode'] ?? 0);

		$visible_columns_raw = trim((string) ($this->fields_values['visible_columns'] ?? ''));
		$chart_label_column = trim((string) ($this->fields_values['chart_label_column'] ?? ''));
		$chart_value_columns_raw = trim((string) ($this->fields_values['chart_value_columns'] ?? ''));
		$chart_type = $this->resolveChartType($this->fields_values['chart_type'] ?? 0);
		$show_second_chart = (int) ($this->fields_values['show_second_chart'] ?? 0);
		$chart2_label_column = trim((string) ($this->fields_values['chart2_label_column'] ?? ''));
		$chart2_value_columns_raw = trim((string) ($this->fields_values['chart2_value_columns'] ?? ''));
		$chart2_type = $this->resolveChartType($this->fields_values['chart2_type'] ?? 0);
		$max_chart_rows_raw = trim((string) ($this->fields_values['max_chart_rows'] ?? '10'));
		$color_theme = $this->resolveColorTheme($this->fields_values['color_theme'] ?? 0);
		$chart_palette_raw = trim((string) ($this->fields_values['chart_palette'] ?? ''));

		$color_ok = $this->resolveNamedColor($this->fields_values['color_ok'] ?? 0, self::NAMED_COLORS[0]);
		$color_warn = $this->resolveNamedColor($this->fields_values['color_warn'] ?? 1, self::NAMED_COLORS[1]);
		$color_error = $this->resolveNamedColor($this->fields_values['color_error'] ?? 2, self::NAMED_COLORS[2]);
		$color_info = $this->resolveNamedColor($this->fields_values['color_info'] ?? 3, self::NAMED_COLORS[3]);
		$status_color_map = trim((string) ($this->fields_values['status_color_map'] ?? ''));

		$error = null;
		$item_name = '';
		$rows = [];
		$columns = [];
		$visible_columns = [];
		$summary = [];
		$status_columns = [];
		$chart_value_columns = [];
		$chart2_value_columns = [];
		$chart_palette = [];
		$color_themes = $this->getColorThemes();
		if (!array_key_exists($color_theme, $color_themes)) {
			$color_theme = 'ocean';
		}

		$max_chart_rows = (int) $max_chart_rows_raw;
		if ($max_chart_rows <= 0) {
			$max_chart_rows = 10;
		}

		if (!$itemids) {
			$error = _('No item selected.');
		}
		else {
			$items = \API::Item()->get([
				'output' => ['itemid', 'name', 'lastvalue'],
				'itemids' => $itemids,
				'webitems' => true
			]);

			if (!$items) {
				$error = _('Selected item not found.');
			}
			else {
				$item = $items[0];
				$item_name = $item['name'];
				$raw = $item['lastvalue'];

				if ($raw === '' || $raw === null) {
					$error = _('Item has no value.');
				}
				else {
					$decoded = json_decode($raw, true);

					if (json_last_error() !== JSON_ERROR_NONE) {
						$error = _('Item does not contain valid JSON.');
					}
					else {
						if (is_array($decoded) && !$this->isListArray($decoded)) {
							$summary = $this->detectSummary($decoded);
						}

						$rows = $this->detectRows($decoded);
						$columns = $this->getColumns($rows);
						$status_columns = $this->detectStatusColumns($columns);

						$detected_chart = $this->detectChartColumns($rows, $columns);

						$visible_columns = $this->parseCsv($visible_columns_raw);
						if (!$visible_columns) {
							$visible_columns = $columns;
						}
						else {
							$visible_columns = $this->resolveColumnNames($columns, $visible_columns);
							if (!$visible_columns) {
								$visible_columns = $columns;
							}
						}

						$resolved_chart_label_column = $this->resolveColumnName($columns, $chart_label_column);
						if ($resolved_chart_label_column !== null) {
							$chart_label_column = $resolved_chart_label_column;
						}
						else {
							$chart_label_column = $detected_chart['label'];
						}

						$chart_value_columns = $this->parseCsv($chart_value_columns_raw);
						if (!$chart_value_columns) {
							$chart_value_columns = $detected_chart['values'];
						}
						else {
							$chart_value_columns = $this->resolveColumnNames($columns, $chart_value_columns);
						}

						if (!in_array($chart_type, self::CHART_TYPES, true)) {
							$chart_type = 'bar';
						}

						$resolved_chart2_label_column = $this->resolveColumnName($columns, $chart2_label_column);
						if ($resolved_chart2_label_column !== null) {
							$chart2_label_column = $resolved_chart2_label_column;
						}
						elseif ($chart2_label_column === '') {
							$chart2_label_column = $chart_label_column;
						}

						$chart2_value_columns = $this->parseCsv($chart2_value_columns_raw);
						if ($chart2_value_columns) {
							$chart2_value_columns = $this->resolveColumnNames($columns, $chart2_value_columns);
						}
						elseif (!$chart2_value_columns && $chart_value_columns) {
							$chart2_value_columns = $chart_value_columns;
						}

						if (!in_array($chart2_type, self::CHART_TYPES, true)) {
							$chart2_type = 'bar';
						}

						foreach ($this->parseCsv($chart_palette_raw) as $c) {
							$chart_palette[] = $this->sanitizeColor($c, '#0284c7');
						}
						if (!$chart_palette && array_key_exists($color_theme, $color_themes)) {
							$chart_palette = $color_themes[$color_theme];
						}
						if (!$chart_palette) {
							$chart_palette = $color_themes['ocean'];
						}

						if (!$rows) {
							$error = _('JSON contains no rows.');
						}
					}
				}
			}
		}

		$this->setResponse(new CControllerResponseData([
			'name' => $this->getInput('name', _('JSON Table')),
			'item_name' => $item_name,
			'rows' => $rows,
			'columns' => $columns,
			'visible_columns' => $visible_columns,
			'summary' => $summary,
			'status_columns' => $status_columns,
			'show_summary' => $show_summary,
			'show_expand' => $show_expand,
			'show_chart' => $show_chart,
			'show_second_chart' => $show_second_chart,
			'dark_header' => $dark_header,
			'compact_mode' => $compact_mode,
			'chart_label_column' => $chart_label_column,
			'chart_value_columns' => $chart_value_columns,
			'chart_type' => $chart_type,
			'chart2_label_column' => $chart2_label_column,
			'chart2_value_columns' => $chart2_value_columns,
			'chart2_type' => $chart2_type,
			'max_chart_rows' => $max_chart_rows,
			'color_theme' => $color_theme,
			'chart_palette' => $chart_palette,
			'color_ok' => $color_ok,
			'color_warn' => $color_warn,
			'color_error' => $color_error,
			'color_info' => $color_info,
			'status_color_map' => $status_color_map,
			'error' => $error,
			'user' => [
				'debug_mode' => $this->getDebugMode()
			]
		]));
	}
}
