package bj.gescol.autonome;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.res.AssetManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.util.TypedValue;
import android.view.Gravity;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * GESCOL Autonome : toute l'application (programme + base de données) fonctionne sur l'appareil,
 * sans PC serveur, sans Wi-Fi et sans Internet. Les données restent dans l'application ;
 * elles s'échangent avec un PC ou la version en ligne par les sauvegardes (.zip).
 */
public class MainActivity extends Activity {

    private static final int CODE_FICHIER = 41;
    private static final int CODE_STOCKAGE = 42;
    private static final int CODE_CAMERA = 43;
    private static final int BLEU = Color.rgb(31, 78, 121);
    private static final int FOND = Color.rgb(244, 246, 249);

    private WebView web;
    private String adresse;
    private ValueCallback<Uri[]> rappelFichier;
    private PermissionRequest demandeCamera;
    private String[] telechargementEnAttente;

    @Override
    protected void onCreate(Bundle etat) {
        super.onCreate(etat);
        getWindow().setStatusBarColor(BLEU);
        afficherDemarrage("Démarrage de GESCOL…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    File web = preparerFichiersWeb();
                    if (!Python.isStarted()) {
                        Python.start(new AndroidPlatform(MainActivity.this));
                    }
                    File donnees = new File(getFilesDir(), "donnees");
                    PyObject url = Python.getInstance().getModule("gescol_android")
                            .callAttr("demarrer", donnees.getAbsolutePath(), web.getAbsolutePath());
                    adresse = url.toString();
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            afficherWeb();
                        }
                    });
                } catch (final Throwable t) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            afficherDemarrage("GESCOL n'a pas pu démarrer :\n" + t.getMessage());
                        }
                    });
                }
            }
        }, "demarrage").start();
    }

    private int dp(int v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private void afficherDemarrage(String message) {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setGravity(Gravity.CENTER);
        col.setBackgroundColor(FOND);
        col.setPadding(dp(24), dp(24), dp(24), dp(24));
        TextView t = new TextView(this);
        t.setText("GESCOL");
        t.setTextColor(BLEU);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 32);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setGravity(Gravity.CENTER);
        col.addView(t);
        TextView s = new TextView(this);
        s.setText("Application autonome – fonctionne sans Internet");
        s.setGravity(Gravity.CENTER);
        s.setPadding(0, dp(4), 0, dp(24));
        col.addView(s);
        if (message.startsWith("Démarrage")) {
            col.addView(new ProgressBar(this));
        }
        TextView m = new TextView(this);
        m.setText(message);
        m.setGravity(Gravity.CENTER);
        m.setPadding(0, dp(16), 0, dp(24));
        col.addView(m);
        TextView c = new TextView(this);
        c.setText("Conception : Maître Aimé FACHE");
        c.setTextColor(Color.GRAY);
        c.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        c.setGravity(Gravity.CENTER);
        col.addView(c);
        setContentView(col);
    }

    // ------------------------------------------------------------------ gabarits et fichiers statiques
    /** Recopie assets/gescol_web vers le stockage de l'application (à l'installation ou après une mise à jour). */
    private File preparerFichiersWeb() throws IOException, PackageManager.NameNotFoundException {
        File cible = new File(getFilesDir(), "gescol_web");
        PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
        String tampon = info.versionCode + "-" + info.lastUpdateTime;
        SharedPreferences prefs = getSharedPreferences("gescol", Context.MODE_PRIVATE);
        if (!tampon.equals(prefs.getString("web", "")) || !new File(cible, "templates/base.html").exists()) {
            supprimer(cible);
            copierAssets(getAssets(), "gescol_web", cible);
            prefs.edit().putString("web", tampon).apply();
        }
        return cible;
    }

    private static void supprimer(File f) {
        File[] enfants = f.listFiles();
        if (enfants != null) {
            for (File e : enfants) {
                supprimer(e);
            }
        }
        f.delete();
    }

    private static void copierAssets(AssetManager am, String chemin, File cible) throws IOException {
        String[] liste = am.list(chemin);
        if (liste == null || liste.length == 0) {  // fichier
            cible.getParentFile().mkdirs();
            try (InputStream in = am.open(chemin); OutputStream out = new FileOutputStream(cible)) {
                byte[] tampon = new byte[16384];
                int n;
                while ((n = in.read(tampon)) > 0) {
                    out.write(tampon, 0, n);
                }
            }
            return;
        }
        cible.mkdirs();
        for (String nom : liste) {
            copierAssets(am, chemin + "/" + nom, new File(cible, nom));
        }
    }

    // ------------------------------------------------------------------ écran GESCOL
    private void afficherWeb() {
        web = new WebView(this);
        WebSettings r = web.getSettings();
        r.setJavaScriptEnabled(true);
        r.setDomStorageEnabled(true);
        r.setLoadWithOverviewMode(true);
        r.setUseWideViewPort(true);
        r.setBuiltInZoomControls(true);
        r.setDisplayZoomControls(false);
        r.setAllowFileAccess(false);
        r.setMediaPlaybackRequiresUserGesture(false);
        r.setSupportMultipleWindows(false);
        r.setUserAgentString(r.getUserAgentString() + " GescolAutonome/1.3");
        CookieManager.getInstance().setAcceptCookie(true);
        web.addJavascriptInterface(new Pont(), "GescolAutonome");

        final String hote = Uri.parse(adresse).getHost();
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView vue, WebResourceRequest demande) {
                Uri u = demande.getUrl();
                if (hote != null && hote.equals(u.getHost())) {
                    return false;
                }
                try {  // liens externes (WhatsApp, téléphone, e-mail, sites) : applications du téléphone
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (ActivityNotFoundException e) {
                    Toast.makeText(MainActivity.this, "Aucune application pour ouvrir ce lien", Toast.LENGTH_SHORT).show();
                }
                return true;
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
                    return false;
                }
                return true;
            }

            @Override
            public void onPermissionRequest(final PermissionRequest demande) {
                // caméra pour les photos d'élèves (seulement pour GESCOL lui-même)
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                            demande.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                        } else {
                            demandeCamera = demande;
                            requestPermissions(new String[]{Manifest.permission.CAMERA}, CODE_CAMERA);
                        }
                    }
                });
            }
        });

        web.setDownloadListener(new android.webkit.DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String disposition, String mime, long taille) {
                telecharger(url, disposition, mime);
            }
        });

        setContentView(web);
        web.loadUrl(adresse + "/");
    }

    /** PDF, Excel, sauvegardes : enregistrés dans « Téléchargements ». */
    private void telecharger(String url, String disposition, String mime) {
        if (Build.VERSION.SDK_INT < 29
                && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            telechargementEnAttente = new String[]{url, disposition, mime};
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
            req.setTitle(nom);
            req.setDescription("GESCOL");
            if (mime != null) {
                req.setMimeType(mime);
            }
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, nom);
            ((DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE)).enqueue(req);
            Toast.makeText(this, "Enregistré dans Téléchargements : " + nom, Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Toast.makeText(this, "Téléchargement impossible : " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] resultats) {
        super.onRequestPermissionsResult(code, permissions, resultats);
        boolean ok = resultats.length > 0 && resultats[0] == PackageManager.PERMISSION_GRANTED;
        if (code == CODE_CAMERA && demandeCamera != null) {
            if (ok) {
                demandeCamera.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
            } else {
                demandeCamera.deny();
            }
            demandeCamera = null;
        } else if (code == CODE_STOCKAGE && telechargementEnAttente != null) {
            String[] t = telechargementEnAttente;
            telechargementEnAttente = null;
            if (ok) {
                telecharger(t[0], t[1], t[2]);
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

    /** Accessible depuis les pages GESCOL. */
    private class Pont {
        @JavascriptInterface
        public boolean autonome() {
            return true;
        }
    }
}
