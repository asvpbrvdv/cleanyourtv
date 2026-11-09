package com.gathin.tvhome;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.LayerDrawable;
import android.graphics.drawable.StateListDrawable;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.util.List;

/** Remote-friendly settings owned by the launcher; system settings stay one row away. */
public final class LauncherSettingsActivity extends Activity {
    private SharedPreferences choices;
    private final TextView[] columnChoices = new TextView[4];
    private final TextView[] rowChoices = new TextView[4];
    private View wallpaperChoice;
    private View animationsChoice;
    private View advancedChoice;
    private View followThemeChoice;
    private TextView wallpaperValue;
    private TextView animationsValue;
    private TextView advancedValue;
    private int columns;
    private int rowsBelowDock;
    private boolean animations;
    private boolean advancedEffects;
    private DotMatrix.Palette palette;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        palette = DotMatrix.palette(Config.load(this).mode);
        DotMatrix.applyMode(this, palette.mode);
        setContentView(R.layout.activity_launcher_settings);
        findViewById(R.id.settingsRoot).setBackground(
                DotMatrix.background(this, palette.background, palette.gridDot));
        wallpaperValue = findViewById(R.id.wallpaperValue);
        animationsValue = findViewById(R.id.animationsValue);
        advancedValue = findViewById(R.id.advancedValue);
        choices = getSharedPreferences(Config.SETTINGS_NAME, MODE_PRIVATE);
        Config config = Config.load(this);
        columns = config.columns;
        rowsBelowDock = config.rowsBelowDock;
        animations = config.animations;
        advancedEffects = config.animations && config.advancedEffects;

        int[] ids = {R.id.columns4, R.id.columns5, R.id.columns6, R.id.columns7};
        for (int i = 0; i < ids.length; i++) {
            final int value = i + 4;
            columnChoices[i] = findViewById(ids[i]);
            columnChoices[i].setOnClickListener(v -> {
                if (columns == value) return;
                columns = value;
                choices.edit().putInt("columns", value).apply();
                setResult(RESULT_OK);
                refresh();
            });
        }
        int[] rowIds = {R.id.rows0, R.id.rows1, R.id.rows2, R.id.rows3};
        for (int i = 0; i < rowIds.length; i++) {
            final int value = i;
            rowChoices[i] = findViewById(rowIds[i]);
            rowChoices[i].setOnClickListener(v -> {
                if (rowsBelowDock == value) return;
                rowsBelowDock = value;
                choices.edit().putInt(Config.ROWS_BELOW_DOCK_KEY, value).apply();
                setResult(RESULT_OK);
                refresh();
            });
        }
        // Keep the numeric choices increasing in the Hebrew reading direction. Reorder the
        // actual views so D-pad focus follows their positions without changing the saved values.
        if (getResources().getBoolean(R.bool.rtl_app_grid)) {
            reverseRow(columnChoices);
            reverseRow(rowChoices);
        }
        wallpaperChoice = findViewById(R.id.wallpaperChoice);
        wallpaperChoice.setOnClickListener(v -> showWallpaperPicker());
        animationsChoice = findViewById(R.id.animationsChoice);
        animationsChoice.setOnClickListener(v -> {
            animations = !animations;
            if (!animations) advancedEffects = false;
            choices.edit().putBoolean("animations", animations)
                    .putBoolean("advanced_effects", advancedEffects).apply();
            setResult(RESULT_OK);
            refresh();
        });
        advancedChoice = findViewById(R.id.advancedChoice);
        advancedChoice.setOnClickListener(v -> {
            if (advancedEffects) {
                setAdvanced(false);
            } else {
                new AlertDialog.Builder(this)
                        .setTitle(R.string.advanced_effects)
                        .setMessage(R.string.advanced_effects_warning)
                        .setPositiveButton(R.string.enable, (dialog, which) -> setAdvanced(true))
                        .setNegativeButton(android.R.string.cancel, null)
                        .show();
            }
        });
        followThemeChoice = findViewById(R.id.followThemeChoice);
        followThemeChoice.setOnClickListener(v -> {
            if (!hasOnTvChoices()) return;
            choices.edit().remove("columns").remove(Config.MODE_KEY).remove(Config.ROWS_BELOW_DOCK_KEY).remove("animations")
                    .remove("advanced_effects").remove(Config.WALLPAPER_CHOICE_KEY).commit();
            Config current = Config.load(this);
            columns = current.columns;
            rowsBelowDock = current.rowsBelowDock;
            animations = current.animations;
            advancedEffects = current.animations && current.advancedEffects;
            setResult(RESULT_OK);
            refresh();
        });
        findViewById(R.id.defaultHomeChoice).setOnClickListener(v -> {
            Toast.makeText(this, R.string.home_settings_help, Toast.LENGTH_LONG).show();
            open(new Intent(Settings.ACTION_HOME_SETTINGS));
        });
        findViewById(R.id.tvSettingsChoice).setOnClickListener(v ->
                open(new Intent(Settings.ACTION_SETTINGS)));
        if (palette.colour()) {
            // Colour mode: each section's dots in its line colour (apps per row yellow, rows below dock lime).
            for (TextView box : columnChoices) box.setBackground(boxBackground(DotMatrix.YELLOW));
            for (TextView box : rowChoices) box.setBackground(boxBackground(DotMatrix.LIME));
        }
        refresh();
        columnChoices[Math.max(0, Math.min(columns - 4, 3))].requestFocus();
    }

    private void reverseRow(TextView[] views) {
        LinearLayout row = (LinearLayout) views[0].getParent();
        row.removeAllViews();
        for (int i = views.length - 1; i >= 0; i--) row.addView(views[i]);
    }

    private void showWallpaperPicker() {
        File dir = Config.dir(this);
        List<File> images = new java.util.ArrayList<>(WallpaperRotation.images(
                dir == null ? null : new File(dir, "wallpapers")));
        // A theme with a single wallpaper.jpg offers that picture too (Config maps the choice back to it).
        File single = dir == null ? null : new File(dir, Config.WALLPAPER_NAME);
        if (single != null && single.isFile()) images.add(0, single);
        String[] labels = new String[images.size() + 1];
        for (int i = 0; i < images.size(); i++) labels[i] = images.get(i).getName();
        labels[images.size()] = getString(R.string.wallpaper_none);
        String current = choices.getString(Config.WALLPAPER_CHOICE_KEY, null);
        int checked = "none".equals(current) ? images.size()
                : indexOf(images, current);
        new AlertDialog.Builder(this)
                .setTitle(R.string.wallpaper_label)
                .setSingleChoiceItems(labels, checked, (dialog, which) -> {
                    dialog.dismiss();
                    if (which == images.size()) {
                        choices.edit().putString(Config.WALLPAPER_CHOICE_KEY, "none").apply();
                    } else {
                        choices.edit().putString(Config.WALLPAPER_CHOICE_KEY,
                                images.get(which).getName()).apply();
                    }
                    setResult(RESULT_OK);
                    Toast.makeText(this, R.string.wallpaper_applied, Toast.LENGTH_SHORT).show();
                    refresh();
                })
                .setNeutralButton(R.string.wallpaper_theme_default, (dialog, which) -> {
                    choices.edit().remove(Config.WALLPAPER_CHOICE_KEY).apply();
                    setResult(RESULT_OK);
                    refresh();
                })
                .setNegativeButton(android.R.string.cancel, null)
                .show();
    }

    private static int indexOf(List<File> images, String name) {
        if (name == null) return -1;
        for (int i = 0; i < images.size(); i++) {
            if (images.get(i).getName().equals(name)) return i;
        }
        return -1;
    }

    private void setAdvanced(boolean enabled) {
        advancedEffects = enabled;
        choices.edit().putBoolean("advanced_effects", enabled).apply();
        setResult(RESULT_OK);
        refresh();
    }

    private void refresh() {
        for (int i = 0; i < columnChoices.length; i++) {
            columnChoices[i].setSelected(columns == i + 4);
        }
        for (int i = 0; i < rowChoices.length; i++) {
            rowChoices[i].setSelected(rowsBelowDock == i);
        }
        setSwitch(animationsValue, animations);
        setSwitch(advancedValue, advancedEffects);
        advancedChoice.setEnabled(animations);
        advancedChoice.setAlpha(animations ? 1f : 0.5f);
        String wallpaperCurrent = choices.getString(Config.WALLPAPER_CHOICE_KEY, null);
        boolean noWallpaper = "none".equals(wallpaperCurrent);
        wallpaperValue.setText(noWallpaper ? getString(R.string.off)
                : wallpaperCurrent != null ? wallpaperCurrent
                : getString(R.string.wallpaper_theme_default));
        // The dot only when a picture is actually shown (a theme default with no wallpaper file shows none).
        Config shown = Config.load(this);
        setDot(wallpaperValue, !noWallpaper && (shown.wallpaper != null || !shown.wallpapers.isEmpty()));
        followThemeChoice.setSelected(!hasOnTvChoices());
    }

    /** ON with an accent dot before it, or OFF. */
    private void setSwitch(TextView value, boolean on) {
        value.setText(on ? R.string.on : R.string.off);
        setDot(value, on);
    }

    private void setDot(TextView value, boolean on) {
        Drawable dot = null;
        if (on) {
            dot = getDrawable(R.drawable.name_dot).mutate();
            if (palette.colour()) dot.setTint(DotMatrix.PURPLE);   // colour mode: the switches' line colour
        }
        value.setCompoundDrawablesRelativeWithIntrinsicBounds(dot, null, null, null);
    }

    /** dm_box_bg.xml with the current-value dot in this colour (colour mode). */
    private Drawable boxBackground(int dotColour) {
        float d = getResources().getDisplayMetrics().density;
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_focused, android.R.attr.state_selected}, withDot(box(true, d), dotColour, d));
        states.addState(new int[]{android.R.attr.state_focused}, box(true, d));
        states.addState(new int[]{android.R.attr.state_selected}, withDot(box(false, d), dotColour, d));
        states.addState(new int[]{}, box(false, d));
        return states;
    }

    private GradientDrawable box(boolean filled, float d) {
        GradientDrawable box = new GradientDrawable();
        box.setCornerRadius(12 * d);
        if (filled) box.setColor(palette.ink);
        else box.setStroke(Math.max(1, Math.round(d)), palette.ink30);
        return box;
    }

    private static Drawable withDot(Drawable box, int colour, float d) {
        GradientDrawable dot = new GradientDrawable();
        dot.setShape(GradientDrawable.OVAL);
        dot.setColor(colour);
        LayerDrawable layers = new LayerDrawable(new Drawable[]{box, dot});
        int size = Math.round(5 * d);
        layers.setLayerSize(1, size, size);
        layers.setLayerGravity(1, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        layers.setLayerInsetBottom(1, Math.round(6 * d));
        return layers;
    }

    private boolean hasOnTvChoices() {
        return choices.contains("columns") || choices.contains(Config.MODE_KEY) || choices.contains(Config.ROWS_BELOW_DOCK_KEY)
                || choices.contains("animations") || choices.contains("advanced_effects")
                || choices.contains(Config.WALLPAPER_CHOICE_KEY);
    }

    private void open(Intent intent) {
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException | SecurityException e) {
            Toast.makeText(this, R.string.not_available, Toast.LENGTH_LONG).show();
        }
    }
}
