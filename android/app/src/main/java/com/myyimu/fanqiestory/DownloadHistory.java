package com.myyimu.fanqiestory;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.UUID;

final class DownloadHistory {
    private static final String PREFS_NAME = "download_history";
    private static final String ENTRIES_KEY = "entries_v1";

    private final SharedPreferences preferences;

    DownloadHistory(Context context) {
        preferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    synchronized JSONArray entries() {
        try {
            return new JSONArray(preferences.getString(ENTRIES_KEY, "[]"));
        } catch (JSONException error) {
            return new JSONArray();
        }
    }

    synchronized JSONArray publicEntries() {
        JSONArray result = new JSONArray();
        JSONArray entries = entries();
        for (int index = 0; index < entries.length(); index++) {
            JSONObject entry = entries.optJSONObject(index);
            if (entry == null) continue;
            try {
                result.put(new JSONObject()
                    .put("id", entry.optString("id"))
                    .put("name", entry.optString("name"))
                    .put("type", entry.optString("type"))
                    .put("savedAt", entry.optLong("savedAt")));
            } catch (JSONException ignored) {
                // Skip a malformed record without losing the other downloads.
            }
        }
        return result;
    }

    synchronized JSONObject find(String id) {
        JSONArray entries = entries();
        for (int index = 0; index < entries.length(); index++) {
            JSONObject entry = entries.optJSONObject(index);
            if (entry != null && id.equals(entry.optString("id"))) return entry;
        }
        return null;
    }

    synchronized boolean add(Uri uri, String name, String type) {
        try {
            JSONObject record = new JSONObject()
                .put("id", UUID.randomUUID().toString())
                .put("uri", uri.toString())
                .put("name", name)
                .put("type", type)
                .put("savedAt", System.currentTimeMillis());
            JSONArray updated = new JSONArray().put(record);
            JSONArray existing = entries();
            for (int index = 0; index < existing.length(); index++) {
                JSONObject entry = existing.optJSONObject(index);
                if (entry != null && !uri.toString().equals(entry.optString("uri"))) {
                    updated.put(entry);
                }
            }
            return preferences.edit().putString(ENTRIES_KEY, updated.toString()).commit();
        } catch (JSONException error) {
            return false;
        }
    }

    synchronized Uri remove(String id) {
        JSONArray updated = new JSONArray();
        JSONArray existing = entries();
        Uri removed = null;
        for (int index = 0; index < existing.length(); index++) {
            JSONObject entry = existing.optJSONObject(index);
            if (entry == null) continue;
            if (id.equals(entry.optString("id"))) {
                removed = Uri.parse(entry.optString("uri"));
            } else {
                updated.put(entry);
            }
        }
        if (removed != null && preferences.edit().putString(ENTRIES_KEY, updated.toString()).commit()) {
            return removed;
        }
        return null;
    }
}
