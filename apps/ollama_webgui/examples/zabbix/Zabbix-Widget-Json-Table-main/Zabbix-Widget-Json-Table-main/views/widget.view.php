<?php

/**
 * @var CView $this
 * @var array $data
 */

$widget = new CWidgetView($data);

if (!empty($data['error'])) {
	$widget->addItem(new CTag('div', true, $data['error']))->show();
	return;
}

$rows = is_array($data['rows'] ?? null) ? $data['rows'] : [];
$columns = is_array($data['columns'] ?? null) ? $data['columns'] : [];
$visible_columns = is_array($data['visible_columns'] ?? null) ? $data['visible_columns'] : $columns;
$summary = is_array($data['summary'] ?? null) ? $data['summary'] : [];
$status_columns = is_array($data['status_columns'] ?? null) ? $data['status_columns'] : [];

$show_summary = !empty($data['show_summary']);
$show_expand = !empty($data['show_expand']);
$show_chart = !empty($data['show_chart']);
$show_second_chart = !empty($data['show_second_chart']);
$dark_header = !empty($data['dark_header']);
$compact_mode = !empty($data['compact_mode']);

$chart_label_column = (string) ($data['chart_label_column'] ?? '');
$chart_value_columns = is_array($data['chart_value_columns'] ?? null) ? $data['chart_value_columns'] : [];
$chart_type = (string) ($data['chart_type'] ?? 'bar');
$chart2_label_column = (string) ($data['chart2_label_column'] ?? '');
$chart2_value_columns = is_array($data['chart2_value_columns'] ?? null) ? $data['chart2_value_columns'] : [];
$chart2_type = (string) ($data['chart2_type'] ?? 'bar');
$max_chart_rows = (int) ($data['max_chart_rows'] ?? 10);
$chart_palette = is_array($data['chart_palette'] ?? null) ? $data['chart_palette'] : ['#0284c7'];

$color_ok = (string) ($data['color_ok'] ?? '#22c55e');
$color_warn = (string) ($data['color_warn'] ?? '#f59e0b');
$color_error = (string) ($data['color_error'] ?? '#ef4444');
$color_info = (string) ($data['color_info'] ?? '#3b82f6');
$status_color_map_raw = (string) ($data['status_color_map'] ?? '');

$container_id = 'json_table_widget_' . uniqid();

$status_color_map = [];
if ($status_color_map_raw !== '') {
	$pairs = explode(',', $status_color_map_raw);
	foreach ($pairs as $pair) {
		$parts = explode('=', $pair, 2);
		if (count($parts) === 2) {
			$key = strtolower(trim($parts[0]));
			$val = trim($parts[1]);
			if ($key !== '' && (preg_match('/^#[0-9a-fA-F]{6}$/', $val) || preg_match('/^#[0-9a-fA-F]{3}$/', $val))) {
				$status_color_map[$key] = $val;
			}
		}
	}
}

$header_bg = $dark_header ? '#334155' : '#e9ecef';
$header_fg = $dark_header ? '#f8fafc' : '#111827';
$row_fg = '#1f2937';
$padding = $compact_mode ? '4px 6px' : '6px 8px';
$font_size = $compact_mode ? '11px' : '12px';
$chart_bar_height = ($chart_type === 'compact-bar') ? '10px' : (($chart_type === 'dot') ? '8px' : '18px');

$css = '
<style>
#'.$container_id.' {
	font-size: '.$font_size.';
	color: '.$row_fg.';
}
#'.$container_id.' .jt-item-name {
	margin-bottom: 8px;
	font-weight: bold;
	color: '.$row_fg.';
}
#'.$container_id.' .jt-summary {
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	margin-bottom: 10px;
}
#'.$container_id.' .jt-card {
	border: 1px solid #d0d7de;
	border-radius: 6px;
	padding: 6px 10px;
	min-width: 120px;
	background: #f8fafc;
	color: '.$row_fg.';
}
#'.$container_id.' .jt-card-key {
	font-size: 11px;
	opacity: 0.8;
	color: #475569;
}
#'.$container_id.' .jt-card-value {
	font-size: 16px;
	font-weight: bold;
	margin-top: 2px;
	color: #111827;
}
#'.$container_id.' .jt-chart-wrap {
	margin-bottom: 12px;
	border: 1px solid #dcdcdc;
	border-radius: 6px;
	padding: 8px;
	background: #f8fafc;
	color: '.$row_fg.';
}
#'.$container_id.' .jt-chart-title {
	font-weight: bold;
	margin-bottom: 8px;
	color: #111827;
}
#'.$container_id.' .jt-chart-row {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 6px 0;
}
#'.$container_id.' .jt-chart-label {
	width: 28%;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	color: '.$row_fg.';
	font-weight: 600;
}
#'.$container_id.' .jt-chart-series-group {
	flex: 1;
	display: flex;
	flex-direction: column;
	gap: 4px;
}
#'.$container_id.' .jt-chart-series-row {
	display: flex;
	align-items: center;
	gap: 8px;
}
#'.$container_id.' .jt-chart-series-name {
	min-width: 90px;
	color: #475569;
	font-size: 11px;
}
#'.$container_id.' .jt-chart-bar-wrap {
	flex: 1;
	background: #e5e7eb;
	border-radius: 4px;
	height: '.$chart_bar_height.';
	overflow: hidden;
}
#'.$container_id.' .jt-chart-bar {
	height: '.$chart_bar_height.';
}
#'.$container_id.' .jt-chart-dot-wrap {
	flex: 1;
	height: '.$chart_bar_height.';
	position: relative;
}
#'.$container_id.' .jt-chart-dot {
	position: absolute;
	top: 50%;
	transform: translate(-50%, -50%);
	width: 10px;
	height: 10px;
	border-radius: 999px;
}
#'.$container_id.' .jt-chart-line-wrap {
	flex: 1;
	height: '.$chart_bar_height.';
	position: relative;
}
#'.$container_id.' .jt-chart-line {
	position: absolute;
	top: 50%;
	left: 0;
	right: 0;
	height: 2px;
	background: #cbd5e1;
	transform: translateY(-50%);
}
#'.$container_id.' .jt-chart-line-point {
	position: absolute;
	top: 50%;
	transform: translate(-50%, -50%);
	width: 10px;
	height: 10px;
	border-radius: 999px;
}
#'.$container_id.' .jt-chart-lollipop-stick {
	position: absolute;
	top: 50%;
	left: 0;
	height: 2px;
	background: #94a3b8;
	transform: translateY(-50%);
}
#'.$container_id.' .jt-chart-area {
	height: '.$chart_bar_height.';
	border-radius: 4px;
}
#'.$container_id.' .jt-chart-value {
	min-width: 60px;
	text-align: right;
	color: #111827;
}
#'.$container_id.' table.jt-table {
	width: 100%;
	border-collapse: collapse;
	background: #ffffff;
	color: '.$row_fg.';
}
#'.$container_id.' table.jt-table th,
#'.$container_id.' table.jt-table td {
	padding: '.$padding.';
	vertical-align: top;
	border-bottom: 1px solid #dcdcdc;
	text-align: left;
	color: '.$row_fg.';
}
#'.$container_id.' table.jt-table th {
	position: sticky;
	top: 0;
	background: '.$header_bg.';
	color: '.$header_fg.';
	z-index: 1;
	font-weight: 700;
	border-bottom: 1px solid #94a3b8;
}
#'.$container_id.' .jt-expand-cell {
	width: 26px;
	text-align: center;
	font-weight: bold;
	color: '.$row_fg.';
}
#'.$container_id.' .jt-details-box {
	padding: 10px;
	background: #f8fafc;
	border-left: 3px solid #94a3b8;
	white-space: pre-wrap;
	word-break: break-word;
	font-family: monospace;
	font-size: 11px;
	color: #111827;
}
#'.$container_id.' .jt-badge {
	display: inline-block;
	padding: 2px 8px;
	border-radius: 12px;
	font-size: 11px;
	font-weight: bold;
	line-height: 16px;
	white-space: nowrap;
	color: #fff;
}
#'.$container_id.' .jt-muted {
	opacity: 0.85;
	color: #475569;
}
</style>
';

function jt_status_color_value($value, $map, $ok, $warn, $error, $info) {
	$v = strtolower(trim((string) $value));

	if (array_key_exists($v, $map)) {
		return $map[$v];
	}

	if (in_array($v, ['ok', 'success', 'succeeded', 'accept', 'accepted', 'pass', 'passed'], true)) {
		return $ok;
	}
	if (in_array($v, ['warn', 'warning', 'medium', 'monitor'], true)) {
		return $warn;
	}
	if (in_array($v, ['failed', 'fail', 'error', 'deny', 'denied', 'high', 'alert', 'critical'], true)) {
		return $error;
	}
	if (in_array($v, ['info', 'running', 'processing', 'low', 'inprogress'], true)) {
		return $info;
	}

	return '#777777';
}

function jt_render_chart_block(array $rows, string $label_column, array $value_columns, string $chart_type, int $max_chart_rows, array $chart_palette): string {
	if ($label_column === '' || empty($value_columns)) {
		return '';
	}

	$chart_rows = [];
	$series_max = [];
	foreach ($value_columns as $series_col) {
		$series_max[$series_col] = 0;
	}

	foreach ($rows as $row) {
		$label = isset($row[$label_column]) ? (string) $row[$label_column] : '';
		if ($label === '') {
			continue;
		}

		$series_values = [];
		$has_numeric = false;
		foreach ($value_columns as $series_col) {
			$val = $row[$series_col] ?? null;
			if (!is_array($val) && !is_object($val) && is_numeric($val)) {
				$num = (float) $val;
				$series_values[$series_col] = $num;
				$has_numeric = true;
				if ($num > $series_max[$series_col]) {
					$series_max[$series_col] = $num;
				}
			}
		}

		if ($has_numeric) {
			$chart_rows[] = ['label' => $label, 'values' => $series_values];
		}
	}

	if (empty($chart_rows)) {
		return '';
	}

	$primary_series = $value_columns[0];
	usort($chart_rows, function($a, $b) use ($primary_series) {
		$av = $a['values'][$primary_series] ?? 0;
		$bv = $b['values'][$primary_series] ?? 0;
		return $bv <=> $av;
	});
	$chart_rows = array_slice($chart_rows, 0, $max_chart_rows);

	$html = '<div class="jt-chart-wrap">';
	$html .= '<div class="jt-chart-title">'.htmlspecialchars($chart_type.' : '.$label_column.' / '.implode(', ', $value_columns), ENT_QUOTES, 'UTF-8').'</div>';

	foreach ($chart_rows as $chart_row) {
		$html .= '<div class="jt-chart-row">';
		$html .= '<div class="jt-chart-label" title="'.htmlspecialchars($chart_row['label'], ENT_QUOTES, 'UTF-8').'">'.htmlspecialchars($chart_row['label'], ENT_QUOTES, 'UTF-8').'</div>';
		$html .= '<div class="jt-chart-series-group">';

		$palette_index = 0;
		foreach ($value_columns as $series_col) {
			if (!array_key_exists($series_col, $chart_row['values'])) {
				continue;
			}

			$series_color = $chart_palette[$palette_index % count($chart_palette)];
			$palette_index++;
			$series_value = $chart_row['values'][$series_col];
			$max_val = $series_max[$series_col] > 0 ? $series_max[$series_col] : 1;
			$width = ($series_value / $max_val) * 100;

			$html .= '<div class="jt-chart-series-row">';
			$html .= '<div class="jt-chart-series-name">'.htmlspecialchars($series_col, ENT_QUOTES, 'UTF-8').'</div>';

			if ($chart_type === 'value-only') {
				$html .= '<div class="jt-chart-value">'.htmlspecialchars((string) $series_value, ENT_QUOTES, 'UTF-8').'</div>';
			}
			elseif ($chart_type === 'dot') {
				$html .= '<div class="jt-chart-dot-wrap"><span class="jt-chart-dot" style="left:'.$width.'%; background:'.htmlspecialchars($series_color, ENT_QUOTES, 'UTF-8').';"></span></div>';
				$html .= '<div class="jt-chart-value">'.htmlspecialchars((string) $series_value, ENT_QUOTES, 'UTF-8').'</div>';
			}
			elseif ($chart_type === 'line') {
				$html .= '<div class="jt-chart-line-wrap"><span class="jt-chart-line"></span><span class="jt-chart-line-point" style="left:'.$width.'%; background:'.htmlspecialchars($series_color, ENT_QUOTES, 'UTF-8').';"></span></div>';
				$html .= '<div class="jt-chart-value">'.htmlspecialchars((string) $series_value, ENT_QUOTES, 'UTF-8').'</div>';
			}
			elseif ($chart_type === 'lollipop') {
				$html .= '<div class="jt-chart-line-wrap"><span class="jt-chart-lollipop-stick" style="width:'.$width.'%;"></span><span class="jt-chart-line-point" style="left:'.$width.'%; background:'.htmlspecialchars($series_color, ENT_QUOTES, 'UTF-8').';"></span></div>';
				$html .= '<div class="jt-chart-value">'.htmlspecialchars((string) $series_value, ENT_QUOTES, 'UTF-8').'</div>';
			}
			else {
				$bar_style = ($chart_type === 'stacked-bar')
					? 'width:'.$width.'%; background:linear-gradient(90deg, '.htmlspecialchars($series_color, ENT_QUOTES, 'UTF-8').', #ffffff);'
					: 'width:'.$width.'%; background:'.htmlspecialchars($series_color, ENT_QUOTES, 'UTF-8').';';
				if ($chart_type === 'soft-area') {
					$bar_style = 'width:'.$width.'%; background:'.htmlspecialchars($series_color, ENT_QUOTES, 'UTF-8').'; opacity:0.35;';
				}
				$html .= '<div class="jt-chart-bar-wrap"><div class="jt-chart-bar jt-chart-area" style="'.$bar_style.'"></div></div>';
				$html .= '<div class="jt-chart-value">'.htmlspecialchars((string) $series_value, ENT_QUOTES, 'UTF-8').'</div>';
			}

			$html .= '</div>';
		}

		$html .= '</div>';
		$html .= '</div>';
	}

	$html .= '</div>';
	return $html;
}

$html = '<div id="'.$container_id.'">';

if (!empty($data['item_name'])) {
	$html .= '<div class="jt-item-name">'.htmlspecialchars(_('Item').': '.$data['item_name'], ENT_QUOTES, 'UTF-8').'</div>';
}

if ($show_summary && !empty($summary)) {
	$html .= '<div class="jt-summary">';
	foreach ($summary as $k => $v) {
		if (is_array($v) || is_object($v)) {
			continue;
		}
		$html .= '<div class="jt-card">';
		$html .= '<div class="jt-card-key">'.htmlspecialchars((string) $k, ENT_QUOTES, 'UTF-8').'</div>';
		$html .= '<div class="jt-card-value">'.htmlspecialchars((string) $v, ENT_QUOTES, 'UTF-8').'</div>';
		$html .= '</div>';
	}
	$html .= '</div>';
}

if ($show_chart) {
	$html .= jt_render_chart_block($rows, $chart_label_column, $chart_value_columns, $chart_type, $max_chart_rows, $chart_palette);
}

if ($show_second_chart) {
	$html .= jt_render_chart_block($rows, $chart2_label_column, $chart2_value_columns, $chart2_type, $max_chart_rows, $chart_palette);
}

$html .= '<table class="jt-table">';
$html .= '<thead><tr>';
if ($show_expand) {
	$html .= '<th></th>';
}
foreach ($visible_columns as $col) {
	$html .= '<th>'.htmlspecialchars((string) $col, ENT_QUOTES, 'UTF-8').'</th>';
}
$html .= '</tr></thead><tbody>';

foreach ($rows as $row) {
	$details = [];
	foreach ($row as $k => $v) {
		if (is_array($v) || is_object($v)) {
			$details[$k] = $v;
		}
	}

	$html .= '<tr>';
	if ($show_expand) {
		$html .= '<td class="jt-expand-cell">'.(!empty($details) ? '+' : '').'</td>';
	}

	foreach ($visible_columns as $col) {
		$value = $row[$col] ?? '';
		$display = '';

		if (is_array($value) || is_object($value)) {
			$display = '<span class="jt-muted">'.htmlspecialchars(json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), ENT_QUOTES, 'UTF-8').'</span>';
		}
		else {
			$string_value = (string) $value;

			if (in_array($col, $status_columns, true)) {
				$bg = jt_status_color_value($string_value, $status_color_map, $color_ok, $color_warn, $color_error, $color_info);
				$display = '<span class="jt-badge" style="background:'.htmlspecialchars($bg, ENT_QUOTES, 'UTF-8').';">'.htmlspecialchars($string_value, ENT_QUOTES, 'UTF-8').'</span>';
			}
			else {
				$display = htmlspecialchars($string_value, ENT_QUOTES, 'UTF-8');
			}
		}

		$html .= '<td>'.$display.'</td>';
	}

	$html .= '</tr>';

	if ($show_expand && !empty($details)) {
		$colspan = count($visible_columns) + 1;
		$html .= '<tr>';
		$html .= '<td colspan="'.$colspan.'"><div class="jt-details-box">'.htmlspecialchars(json_encode($details, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), ENT_QUOTES, 'UTF-8').'</div></td>';
		$html .= '</tr>';
	}
}

$html .= '</tbody></table>';
$html .= '</div>';

$widget
	->addItem($css)
	->addItem($html)
	->show();
