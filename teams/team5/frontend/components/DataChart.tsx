// frontend/components/DataChart.tsx

"use client";

import React from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { ChartData } from "@/lib/types";

interface DataChartProps {
  chartData: ChartData;
}

function ValueDisplay({ chartData }: DataChartProps) {
  const value = chartData.data[0]?.[chartData.yKey];
  const numValue = typeof value === "number" ? value : parseFloat(String(value));
  const isAboveAverage = numValue > 1;
  const isBelowAverage = numValue < 1;

  return (
    <div className="bg-gray-50 rounded-lg p-4 text-center">
      <p className="text-xs text-gray-500 mb-1">{chartData.title}</p>
      <p
        className={`text-3xl font-bold ${
          isAboveAverage
            ? "text-red-600"
            : isBelowAverage
            ? "text-green-600"
            : "text-gray-900"
        }`}
      >
        {typeof numValue === "number" && !isNaN(numValue)
          ? numValue.toFixed(2)
          : String(value)}
      </p>
      {chartData.unit && (
        <p className="text-xs text-gray-500 mt-1">{chartData.unit}</p>
      )}
      {!isNaN(numValue) && (
        <p
          className={`text-xs mt-1 ${
            isAboveAverage
              ? "text-red-500"
              : isBelowAverage
              ? "text-green-500"
              : "text-gray-500"
          }`}
        >
          {isAboveAverage
            ? "Hoger dan gemiddeld"
            : isBelowAverage
            ? "Lager dan gemiddeld"
            : "Gemiddeld"}
        </p>
      )}
    </div>
  );
}

export default function DataChart({ chartData }: DataChartProps) {
  if (chartData.type === "value") {
    return <ValueDisplay chartData={chartData} />;
  }

  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <p className="text-xs font-medium text-gray-700 mb-3">
        {chartData.title}
      </p>
      <ResponsiveContainer width="100%" height={240}>
        {chartData.type === "line" ? (
          <LineChart data={chartData.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey={chartData.xKey}
              tick={{ fontSize: 11, fill: "#6b7280" }}
              axisLine={{ stroke: "#d1d5db" }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#6b7280" }}
              axisLine={{ stroke: "#d1d5db" }}
              unit={chartData.unit ? ` ${chartData.unit}` : ""}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />
            <Line
              type="monotone"
              dataKey={chartData.yKey}
              stroke="#2563eb"
              strokeWidth={2}
              dot={{ r: 3, fill: "#2563eb" }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        ) : (
          <BarChart data={chartData.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey={chartData.xKey}
              tick={{ fontSize: 11, fill: "#6b7280" }}
              axisLine={{ stroke: "#d1d5db" }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#6b7280" }}
              axisLine={{ stroke: "#d1d5db" }}
              unit={chartData.unit ? ` ${chartData.unit}` : ""}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />
            <Bar
              dataKey={chartData.yKey}
              fill="#2563eb"
              radius={[4, 4, 0, 0]}
              maxBarSize={48}
            />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
