import { useEffect,useRef } from 'react';
import {
CognitiveTrace
} from "./cognitiveVisualization";
import type { EvaluationReport,HistoryItem } from './types';

import { LineChart as EChartsLineChart,RadarChart as EChartsRadarChart } from "echarts/charts";
import { GridComponent,RadarComponent,TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { formatDate } from './api';

echarts.use([EChartsLineChart, EChartsRadarChart, GridComponent, RadarComponent, TooltipComponent, CanvasRenderer]);

// Canvas charts use the same computed tokens as the surrounding interface.
function readChartTheme(element: HTMLElement) {
  const style = getComputedStyle(element);
  const token = (name: string) => style.getPropertyValue(name).trim();
  const fontSize = parseFloat(getComputedStyle(document.documentElement).fontSize)
    * parseFloat(token('--text-caption-size'));
  const textStyle = { color: token('--text-muted'), fontFamily: style.fontFamily, fontSize };
  return {
    textStyle,
    accent: token('--teal'),
    surface: token('--surface'),
    mutedSurface: token('--surface-muted'),
    border: token('--border'),
    tooltip: {
      confine: true,
      backgroundColor: token('--surface'),
      borderColor: token('--border'),
      textStyle: { ...textStyle, color: token('--text-body') },
    },
  };
}

export function CognitiveStrengthChart({ trace }: { trace: CognitiveTrace }) {
  const chartRef = useRef<HTMLDivElement>(null);
  const values = [trace.initial_misconception?.strength ?? 0, ...trace.rounds.map((round) => round.misconception_after?.strength ?? 0)];
  useEffect(() => {
    if (!chartRef.current || values.length < 2) return;
    const chart = echarts.init(chartRef.current);
    const theme = readChartTheme(chartRef.current);
    chart.setOption({
      animation: false,
      textStyle: theme.textStyle,
      tooltip: { ...theme.tooltip, trigger: "axis" },
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: values.map((_, index) => index === 0 ? "初始" : `R${index}`), axisLabel: theme.textStyle, axisLine: { lineStyle: { color: theme.border } }, axisTick: { show: false } },
      yAxis: { type: "value", min: 0, max: 1, axisLabel: theme.textStyle, splitLine: { lineStyle: { color: theme.border } } },
      series: [{ type: "line", data: values, smooth: false, symbol: "circle", symbolSize: 7, lineStyle: { color: theme.accent, width: 2 }, itemStyle: { color: theme.accent }, areaStyle: { color: theme.accent, opacity: .08 } }],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); chart.dispose(); };
  }, [trace, values.length]);
  return <div className="strength-chart" ref={chartRef} aria-label="错误认知强度变化图" />;
}

export function RadarChart({ report }: { report: EvaluationReport }) {
  const chartRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!chartRef.current || [report.knowledge_accuracy, report.questioning, report.feedback, report.misconception_diagnosis, report.scaffolding].some(v => v == null)) return;
    const chart = echarts.init(chartRef.current);
    const theme = readChartTheme(chartRef.current);
    const radarLayout = () => {
      const compact = chart.getWidth() < 340;
      const fontSize = theme.textStyle.fontSize;
      return {
        radius: Math.max(24, Math.min(chart.getWidth() / 2 - fontSize * (compact ? 3.2 : 5.5) - 12, chart.getHeight() / 2 - fontSize * 3)),
        axisName: {
          ...theme.textStyle,
          lineHeight: fontSize * 1.5,
          formatter: (name: string) => compact && name.length > 3 ? `${name.slice(0, 3)}\n${name.slice(3)}` : name,
        },
      };
    };
    chart.setOption({
      animation: false,
      textStyle: theme.textStyle,
      tooltip: { ...theme.tooltip, trigger: "item" },
      radar: {
        ...radarLayout(),
        indicator: [
          { name: "知识准确性", max: 100 },
          { name: "提问与引导", max: 100 },
          { name: "教学反馈", max: 100 },
          { name: "错误诊断", max: 100 },
          { name: "支架式教学", max: 100 },
        ],
        splitNumber: 4,
        splitArea: { areaStyle: { color: [theme.surface, theme.mutedSurface] } },
        splitLine: { lineStyle: { color: theme.border } },
        axisLine: { lineStyle: { color: theme.border } },
      },
      series: [{
        type: "radar",
        data: [{
          value: [
            report.knowledge_accuracy,
            report.questioning,
            report.feedback,
            report.misconception_diagnosis,
            report.scaffolding,
          ],
          name: "本次实训",
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { color: theme.accent, width: 2 },
          itemStyle: { color: theme.accent },
          areaStyle: { color: theme.accent, opacity: .08 },
        }],
      }],
    });
    const resize = () => {
      chart.resize();
      chart.setOption({ radar: radarLayout() });
    };
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [report]);
  if ([report.knowledge_accuracy, report.questioning, report.feedback, report.misconception_diagnosis, report.scaffolding].some(v => v == null)) return <p className="fallback-copy">部分维度尚未评估，暂不绘制雷达图；请查看各维度证据。</p>;
  return <div className="radar-chart" ref={chartRef} aria-label="五维能力雷达图" />;
}

export function GrowthChart({ items }: { items: HistoryItem[] }) {
  const chartRef = useRef<HTMLDivElement>(null);
  const scoredItems = items.filter((item): item is HistoryItem & { overall_score: number } => item.overall_score !== null);
  useEffect(() => {
    if (!chartRef.current || scoredItems.length < 2) return;
    const chart = echarts.init(chartRef.current);
    const theme = readChartTheme(chartRef.current);
    chart.setOption({
      animation: false,
      textStyle: theme.textStyle,
      tooltip: { ...theme.tooltip, trigger: "axis" },
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: scoredItems.map((item) => formatDate(item.started_at)), axisLabel: { ...theme.textStyle, hideOverlap: true }, axisLine: { lineStyle: { color: theme.border } }, axisTick: { show: false } },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: theme.textStyle, splitLine: { lineStyle: { color: theme.border } } },
      series: [{ type: "line", data: scoredItems.map((item) => item.overall_score), smooth: false, symbol: "circle", symbolSize: 7, lineStyle: { color: theme.accent, width: 2 }, itemStyle: { color: theme.accent }, areaStyle: { color: theme.accent, opacity: .08 } }],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); chart.dispose(); };
  }, [items, scoredItems.length]);
  return scoredItems.length > 1 ? <div className="growth-chart" ref={chartRef} aria-label="实训总分成长曲线" /> : null;
}
