import * as mock from '../mock'
import {
  adaptAlerts,
  adaptOverview,
  adaptRecommendationAction,
  adaptRecommendations,
  adaptResources,
  adaptTraffic,
} from './adapters.js'

// Flip VITE_USE_MOCK=false in .env to call the FastAPI backend
const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false'
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const local = (value, ms = 250) =>
  new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), ms))

async function http(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`Request to ${path} failed (${res.status})`)
  return res.json()
}

export const getOverview = () =>
  USE_MOCK ? local(mock.overview) : http('/overview').then(adaptOverview)
export const getResources = () =>
  USE_MOCK ? local(mock.resources) : http('/resources').then(adaptResources)
export const getAlerts = () =>
  USE_MOCK ? local(mock.alerts) : http('/alerts').then(adaptAlerts)
export const getTraffic = () =>
  USE_MOCK ? local(mock.traffic) : http('/traffic').then(adaptTraffic)
export const getRecommendations = () =>
  USE_MOCK ? local(mock.recommendations) : http('/recommendations').then(adaptRecommendations)

// action: 'pending' | 'approved' | 'dismissed'
export const actOnRecommendation = (id, action) =>
  USE_MOCK
    ? local({ id, state: action })
    : http(`/recommendations/${id}/action`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      }).then(adaptRecommendationAction)

// status: 'open' | 'investigating' | 'resolved' | 'dismissed'
export const updateAlertStatus = (id, status) =>
  USE_MOCK
    ? local({ id, status })
    : http(`/alerts/${encodeURIComponent(id)}/status`, {
        method: 'POST',
        body: JSON.stringify({ status }),
      }).then((res) => {
        const item = res?.alert ?? res ?? {}
        const nextStatus = String(item.status ?? status).toLowerCase()
        const out = {
          id: String(item.alert_id ?? item.id ?? id),
          status: nextStatus,
        }
        if (res?.previous_status != null) {
          out.previousStatus = String(res.previous_status).toLowerCase()
        }
        if (res?.message != null) {
          out.message = String(res.message)
        }
        return out
      })
