package bj.gescol.app;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/**
 * GESCOL pour Android : affiche l'application GESCOL du serveur de l'école
 * (PC de l'école sur le Wi-Fi, ou version en ligne).
 */
public class MainActivity extends Activity {

    private static final String PREFS = "gescol";
    private static final String CLE_SERVEUR = "serveur";
    private static final int CODE_FICHIER = 41;
    private static final int CODE_STOCKAGE = 42;
    private static final int BLEU = Color.rgb(31, 78, 121);
    private static final int FOND = Color.rgb(244, 246, 249);
    private static final int ROUGE = Color.rgb(180, 35, 24);

    private WebView web;
    private ValueCallback<Uri[]> rappelFichier;
    private String telechargementEnAttente;
    private String typeEnAttente;
    private String dispositionEnAttente;

    @Override
    protected void onCreate(Bundle etat) {
        super.onCreate(etat);
        getWindow().setStatusBarColor(BLEU);
        String serveur = lireServeur();
        if (serveur == null) {
            afficherConfiguration(null);
        } else {
            afficherWeb(serveur, etat);
        }
    }

    // ------------------------------------------------------------------ préférences
    private String lireServeur() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(CLE_SERVEUR, null);
    }

    private void enregistrerServeur(String url) {
        SharedPreferences.Editor e = getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit();
        if (url == null) {
            e.remove(CLE_SERVEUR);
        } else {
            e.putString(CLE_SERVEUR, url);
        }
        e.apply();
    }

    static String normaliser(String saisie) {
        String s = saisie == null ? "" : saisie.trim();
        if (s.isEmpty()) {
            return null;
        }
        if (!s.startsWith("http://") && !s.startsWith("https://")) {
            s = "http://" + s;
        }
        while (s.endsWith("/")) {
            s = s.substring(0, s.length() - 1);
        }
        Uri u = Uri.parse(s);
        if (u.getHost() == null || u.getHost().isEmpty()) {
            return null;
        }
        return s;
    }

    private int dp(int v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    /** Détruit la WebView courante après la fin du rappel en cours (jamais pendant). */
    private void libererWeb() {
        final WebView ancienne = web;
        web = null;
        if (ancienne != null) {
            new Handler(Looper.getMainLooper()).post(new Runnable() {
                @Override
                public void run() {
                    ancienne.stopLoading();
                    ancienne.destroy();
                }
            });
        }
    }

    // ------------------------------------------------------------------ écran de configuration
    private void afficherConfiguration(String message) {
        libererWeb();
        ScrollView defil = new ScrollView(this);
        defil.setBackgroundColor(FOND);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(dp(24), dp(40), dp(24), dp(24));
        defil.addView(col);

        TextView titre = new TextView(this);
        titre.setText("GESCOL");
        titre.setTextColor(BLEU);
        titre.setTextSize(TypedValue.COMPLEX_UNIT_SP, 30);
        titre.setTypeface(Typeface.DEFAULT_BOLD);
        col.addView(titre);

        TextView sous = new TextView(this);
        sous.setText("Gestion d'établissement scolaire");
        sous.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        sous.setPadding(0, 0, 0, dp(24));
        col.addView(sous);

        if (message != null) {
            TextView err = new TextView(this);
            err.setText(message);
            err.setTextColor(ROUGE);
            err.setPadding(0, 0, 0, dp(16));
            col.addView(err);
        }

        TextView lib = new TextView(this);
        lib.setText("Adresse du serveur GESCOL de votre école");
        lib.setTypeface(Typeface.DEFAULT_BOLD);
        col.addView(lib);

        final EditText champ = new EditText(this);
        champ.setHint("ex. 192.168.1.10:5000");
        champ.setSingleLine(true);
        champ.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        champ.setImeOptions(EditorInfo.IME_ACTION_GO);
        String actuel = lireServeur();
        if (actuel != null) {
            champ.setText(actuel);
        }
        col.addView(champ, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView aide = new TextView(this);
        aide.setText("• École équipée d'un PC serveur : recopiez l'adresse affichée dans la fenêtre « GESCOL Serveur » "
                + "(la tablette doit être sur le même Wi-Fi).\n"
                + "• Version en ligne : saisissez l'adresse internet complète, par exemple https://monecole.pythonanywhere.com");
        aide.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        aide.setPadding(0, dp(8), 0, dp(20));
        col.addView(aide);

        Button ok = new Button(this);
        ok.setText("Se connecter");
        ok.setTextColor(Color.WHITE);
        ok.setBackgroundColor(BLEU);
        col.addView(ok, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)));

        TextView credit = new TextView(this);
        credit.setText("Conception : Ma\u00eetre Aim\u00e9 FACHE");
        credit.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        credit.setTextColor(Color.GRAY);
        credit.setGravity(android.view.Gravity.CENTER);
        credit.setPadding(0, dp(28), 0, 0);
        col.addView(credit);

        final Runnable valider = new Runnable() {
            @Override
            public void run() {
                String url = normaliser(champ.getText().toString());
                if (url == null) {
                    Toast.makeText(MainActivity.this, "Adresse invalide", Toast.LENGTH_SHORT).show();
                    return;
                }
                enregistrerServeur(url);
                afficherWeb(url, null);
            }
        };
        ok.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                valider.run();
            }
        });
        champ.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override
            public boolean onEditorAction(TextView v, int actionId, android.view.KeyEvent event) {
                valider.run();
                return true;
            }
        });
        setContentView(defil);
    }

    // ------------------------------------------------------------------ écran « serveur injoignable »
    private void afficherErreur(final String serveur) {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setGravity(Gravity.CENTER_VERTICAL);
        col.setBackgroundColor(FOND);
        col.setPadding(dp(24), dp(24), dp(24), dp(24));

        TextView t = new TextView(this);
        t.setText("Serveur GESCOL injoignable");
        t.setTextColor(BLEU);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        col.addView(t);

        TextView m = new TextView(this);
        m.setText("Adresse : " + serveur + "\n\nVérifiez que l'appareil est connecté au Wi-Fi de l'école "
                + "(ou à Internet pour la version en ligne) et que le PC serveur est allumé avec GESCOL ouvert.");
        m.setPadding(0, dp(12), 0, dp(24));
        col.addView(m);

        Button reessayer = new Button(this);
        reessayer.setText("Réessayer");
        reessayer.setTextColor(Color.WHITE);
        reessayer.setBackgroundColor(BLEU);
        reessayer.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                afficherWeb(serveur, null);
            }
        });
        col.addView(reessayer, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)));

        Button changer = new Button(this);
        changer.setText("Changer l'adresse du serveur");
        changer.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                afficherConfiguration(null);
            }
        });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52));
        lp.topMargin = dp(12);
        col.addView(changer, lp);
        libererWeb();
        setContentView(col);
    }

    // ------------------------------------------------------------------ application web
    private void afficherWeb(final String serveur, Bundle etat) {
        web = new WebView(this);
        WebSettings r = web.getSettings();
        r.setJavaScriptEnabled(true);
        r.setDomStorageEnabled(true);
        r.setLoadWithOverviewMode(true);
        r.setUseWideViewPort(true);
        r.setBuiltInZoomControls(true);
        r.setDisplayZoomControls(false);
        r.setAllowFileAccess(false);
        r.setSupportMultipleWindows(false); // les liens target=_blank (PDF) restent dans l'application
        r.setUserAgentString(r.getUserAgentString() + " GescolAndroid/1.1");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);

        final String hote = Uri.parse(serveur).getHost();
        web.addJavascriptInterface(new Pont(), "GescolAndroid");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView vue, WebResourceRequest demande) {
                Uri u = demande.getUrl();
                if (hote != null && hote.equals(u.getHost())) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (ActivityNotFoundException e) {
                    Toast.makeText(MainActivity.this, "Aucune application pour ouvrir ce lien", Toast.LENGTH_SHORT).show();
                }
                return true;
            }

            @Override
            public void onReceivedError(WebView vue, WebResourceRequest demande, WebResourceError erreur) {
                if (demande.isForMainFrame()) {
                    afficherErreur(serveur);
                }
            }

            @Override
            public void onPageFinished(WebView vue, String url) {
                CookieManager.getInstance().flush();
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView vue, ValueCallback<Uri[]> rappel, FileChooserParams params) {
                if (rappelFichier != null) {
                    rappelFichier.onReceiveValue(null);
                }
                rappelFichier = rappel;
                try {
                    startActivityForResult(params.createIntent(), CODE_FICHIER);
                } catch (ActivityNotFoundException e) {
                    rappelFichier = null;
                    Toast.makeText(MainActivity.this, "Impossible d'ouvrir la galerie", Toast.LENGTH_SHORT).show();
                    return false;
                }
                return true;
            }
        });

        web.setDownloadListener(new android.webkit.DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String disposition, String mime, long taille) {
                telecharger(url, disposition, mime);
            }
        });

        setContentView(web);
        if (etat != null) {
            web.restoreState(etat);
        } else {
            web.loadUrl(serveur + "/");
        }
    }

    /** PDF (bulletins, reçus, certificats), CSV, sauvegardes : via le gestionnaire de téléchargements. */
    private void telecharger(String url, String disposition, String mime) {
        if (Build.VERSION.SDK_INT < 29
                && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            telechargementEnAttente = url;
            dispositionEnAttente = disposition;
            typeEnAttente = mime;
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, CODE_STOCKAGE);
            return;
        }
        try {
            String nom = URLUtil.guessFileName(url, disposition, mime);
            DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
            String cookies = CookieManager.getInstance().getCookie(url);
            if (cookies != null) {
                req.addRequestHeader("Cookie", cookies);
            }
            req.addRequestHeader("User-Agent", web != null ? web.getSettings().getUserAgentString() : "GescolAndroid");
            req.setTitle(nom);
            req.setDescription("GESCOL");
            if (mime != null) {
                req.setMimeType(mime);
            }
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, nom);
            DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            dm.enqueue(req);
            Toast.makeText(this, "Téléchargement de " + nom + " (voir les notifications)", Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Toast.makeText(this, "Téléchargement impossible : " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] resultats) {
        super.onRequestPermissionsResult(code, permissions, resultats);
        if (code == CODE_STOCKAGE && telechargementEnAttente != null) {
            String url = telechargementEnAttente;
            telechargementEnAttente = null;
            if (resultats.length > 0 && resultats[0] == PackageManager.PERMISSION_GRANTED) {
                telecharger(url, dispositionEnAttente, typeEnAttente);
            } else {
                Toast.makeText(this, "Autorisation refusée : le document ne peut pas être enregistré.", Toast.LENGTH_LONG).show();
            }
        }
    }

    @Override
    protected void onActivityResult(int code, int resultat, Intent donnees) {
        super.onActivityResult(code, resultat, donnees);
        if (code == CODE_FICHIER && rappelFichier != null) {
            rappelFichier.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultat, donnees));
            rappelFichier = null;
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle etat) {
        super.onSaveInstanceState(etat);
        if (web != null) {
            web.saveState(etat);
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }

    /** Appelé depuis les pages GESCOL (bouton « Changer de serveur »). */
    private class Pont {
        @JavascriptInterface
        public void changerServeur() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    afficherConfiguration(null);
                }
            });
        }

        @JavascriptInterface
        public String serveur() {
            String s = lireServeur();
            return s == null ? "" : s;
        }
    }
}
