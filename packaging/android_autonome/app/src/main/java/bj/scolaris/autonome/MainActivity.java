package bj.scolaris.autonome;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.provider.MediaStore;
import android.content.ContentValues;
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
 * SCOLARIS Autonome : toute l'application (programme + base de données) fonctionne sur l'appareil,
 * sans PC serveur, sans Wi-Fi et sans Internet. Les données restent dans l'application ;
 * elles s'échangent avec un PC ou la version en ligne par les sauvegardes (.zip).
 */
public class MainActivity extends Activity {

    private static final int CODE_FICHIER = 41;
    private static final int CODE_STOCKAGE = 42;
    private static final int CODE_CAMERA_FICHIER = 44;
    private static final int CODE_CAMERA = 43;
    private static final int BLEU = Color.rgb(31, 78, 121);
    private static final int FOND = Color.rgb(244, 246, 249);

    private WebView web;
    /** Vrai juste après une installation ou une mise à jour : le cache de l'écran (anciennes pages) est vidé. */
    private volatile boolean misAJour = false;
    private String adresse;
    private ValueCallback<Uri[]> rappelFichier;
    private Uri photoUri;
    private WebChromeClient.FileChooserParams paramsEnAttente;
    private PermissionRequest demandeCamera;
    private String[] telechargementEnAttente;
    private String[] fichierEnAttente;
    private static final int CODE_STOCKAGE_PAGE = 47;

    @Override
    protected void onCreate(Bundle etat) {
        super.onCreate(etat);
        getWindow().setStatusBarColor(BLEU);
        afficherDemarrage("Démarrage de SCOLARIS…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    File web = preparerFichiersWeb();
                    if (!Python.isStarted()) {
                        Python.start(new AndroidPlatform(MainActivity.this));
                    }
                    File donnees = new File(getFilesDir(), "donnees");
                    PyObject url = Python.getInstance().getModule("scolaris_android")
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
                            afficherDemarrage("SCOLARIS n'a pas pu démarrer :\n" + t.getMessage());
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
        t.setText("SCOLARIS");
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
        c.setText("SCOLARIS · Conception : Maître Aimé FACHOLA");
        c.setTextColor(Color.GRAY);
        c.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        c.setGravity(Gravity.CENTER);
        col.addView(c);
        setContentView(col);
    }

    // ------------------------------------------------------------------ gabarits et fichiers statiques
    /** Recopie assets/scolaris_web vers le stockage de l'application (à l'installation ou après une mise à jour). */
    private File preparerFichiersWeb() throws IOException, PackageManager.NameNotFoundException {
        File cible = new File(getFilesDir(), "scolaris_web");
        PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
        String tampon = info.versionCode + "-" + info.lastUpdateTime;
        SharedPreferences prefs = getSharedPreferences("scolaris", Context.MODE_PRIVATE);
        if (!tampon.equals(prefs.getString("web", "")) || !new File(cible, "templates/base.html").exists()) {
            supprimer(cible);
            copierAssets(getAssets(), "scolaris_web", cible);
            misAJour = true;
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

    // ------------------------------------------------------------------ écran SCOLARIS
    private void afficherWeb() {
        web = new WebView(this);
        if (misAJour) {
            web.clearCache(true);   // pas d'anciennes pages ni d'anciens fichiers de la version précédente
        }
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
        r.setUserAgentString(r.getUserAgentString() + " ScolarisAutonome/1.3");
        CookieManager.getInstance().setAcceptCookie(true);
        web.addJavascriptInterface(new Pont(), "ScolarisAutonome");

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
                return ouvrirChoixFichier(rappel, params);
            }

            @Override
            public void onPermissionRequest(final PermissionRequest demande) {
                // caméra pour les photos d'élèves (seulement pour SCOLARIS lui-même)
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

    /** v2.2 — PDF, Word, Excel, ZIP, sauvegardes : enregistrés dans « Téléchargements / SCOLARIS » avec leur vrai nom,
     *  puis « Ouvrir » ou « Partager ». Le fichier est lu directement (pas de second téléchargement par le système). */
    private void telecharger(String url, String disposition, String mime) {
        if (Fichiers.autorisationNecessaire(this)) {
            telechargementEnAttente = new String[]{url, disposition, mime};
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, CODE_STOCKAGE);
            return;
        }
        if (url != null && url.startsWith("blob:")) {   // fichier fabriqué dans la page : la page l'envoie au pont
            web.evaluateJavascript("(function(){fetch('" + url.replace("'", "\\'") + "').then(function(r){return r.blob();})"
                    + ".then(function(b){window.scolarisGarderBlob && window.scolarisGarderBlob(b,'document');});})()", null);
            return;
        }
        Toast.makeText(this, "Téléchargement en cours…", Toast.LENGTH_SHORT).show();
        Fichiers.telecharger(this, url, web != null ? web.getSettings().getUserAgentString() : null, disposition, mime, new Fichiers.Fin() {
            @Override
            public void fini(Uri uri, String nom, String type, String erreur) {
                Fichiers.proposer(MainActivity.this, uri, nom, type, erreur);
            }
        });
    }

    /** Fichier reçu de la page (formulaire envoyé, document fabriqué dans la page), en base 64. */
    private void enregistrerDepuisPage(final String nom, final String mime, final String base64) {
        if (Fichiers.autorisationNecessaire(this)) {
            fichierEnAttente = new String[]{nom, mime, base64};
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, CODE_STOCKAGE_PAGE);
            return;
        }
        final byte[] octets;
        try {
            octets = android.util.Base64.decode(base64 == null ? "" : base64, android.util.Base64.DEFAULT);
        } catch (IllegalArgumentException e) {
            Toast.makeText(this, "Fichier illisible", Toast.LENGTH_SHORT).show();
            return;
        }
        new Thread(new Runnable() {
            @Override
            public void run() {
                Fichiers.enregistrer(MainActivity.this, Fichiers.nomFichier(null, nom == null || nom.isEmpty() ? "document" : nom, mime),
                        mime, new java.io.ByteArrayInputStream(octets), new Fichiers.Fin() {
                            @Override
                            public void fini(Uri uri, String n, String type, String erreur) {
                                Fichiers.proposer(MainActivity.this, uri, n, type, erreur);
                            }
                        });
            }
        }, "enregistrement").start();
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] resultats) {
        super.onRequestPermissionsResult(code, permissions, resultats);
        if (code == CODE_CAMERA_FICHIER) {
            WebChromeClient.FileChooserParams p = paramsEnAttente;
            paramsEnAttente = null;
            if (p != null) {
                lancerChoix(p, true);
            }
            return;
        }
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
        } else if (code == CODE_STOCKAGE_PAGE && fichierEnAttente != null) {
            String[] t = fichierEnAttente;
            fichierEnAttente = null;
            if (ok) {
                enregistrerDepuisPage(t[0], t[1], t[2]);
            }
        }
    }

    /** v1.7 : choix d'une photo — appareil photo (avant ou arrière, au choix dans l'appareil photo du téléphone)
     *  ou galerie / fichiers. Indispensable quand SCOLARIS est servi en http sur le Wi-Fi de l'école : la caméra
     *  intégrée à la page (getUserMedia) n'y est pas disponible. */
    private boolean ouvrirChoixFichier(ValueCallback<Uri[]> rappel, WebChromeClient.FileChooserParams params) {
        if (rappelFichier != null) {
            rappelFichier.onReceiveValue(null);
        }
        rappelFichier = rappel;
        boolean image = false;
        String[] types = params.getAcceptTypes();
        if (types == null || types.length == 0) {
            image = true;
        } else {
            for (String t : types) {
                if (t == null || t.isEmpty() || t.startsWith("image") || t.equals("*/*")) {
                    image = true;
                }
            }
        }
        if (image && checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            paramsEnAttente = params;
            requestPermissions(new String[]{Manifest.permission.CAMERA}, CODE_CAMERA_FICHIER);
            return true;
        }
        return lancerChoix(params, image);
    }

    private boolean lancerChoix(WebChromeClient.FileChooserParams params, boolean image) {
        Intent galerie = params.createIntent();
        Intent aLancer = galerie;
        photoUri = null;
        if (image && checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            Intent photo = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
            try {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Images.Media.DISPLAY_NAME, "scolaris_" + System.currentTimeMillis() + ".jpg");
                v.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                if (Build.VERSION.SDK_INT >= 29) {
                    v.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/SCOLARIS");
                }
                photoUri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v);
            } catch (Exception e) {
                photoUri = null;
            }
            if (photoUri != null) {
                photo.putExtra(MediaStore.EXTRA_OUTPUT, photoUri);
                photo.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                aLancer = Intent.createChooser(galerie, "Photo : appareil photo ou galerie");
                aLancer.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{photo});
            }
        }
        try {
            startActivityForResult(aLancer, CODE_FICHIER);
        } catch (ActivityNotFoundException e) {
            oublierPhoto();
            if (rappelFichier != null) {
                rappelFichier.onReceiveValue(null);
            }
            rappelFichier = null;
            Toast.makeText(this, "Impossible d'ouvrir l'appareil photo ou la galerie", Toast.LENGTH_SHORT).show();
            return false;
        }
        return true;
    }

    /** Photo prise par l'appareil photo : retournée à la page ; sinon, l'emplacement réservé est supprimé. */
    private void resultatChoix(int resultat, Intent donnees) {
        Uri[] r = null;
        if (resultat == RESULT_OK) {
            boolean viaGalerie = donnees != null && (donnees.getData() != null || donnees.getClipData() != null);
            if (viaGalerie) {
                r = WebChromeClient.FileChooserParams.parseResult(resultat, donnees);
                oublierPhoto();
            } else if (photoUri != null) {
                r = new Uri[]{photoUri};
            }
        } else {
            oublierPhoto();
        }
        photoUri = null;
        if (rappelFichier != null) {
            rappelFichier.onReceiveValue(r);
        }
        rappelFichier = null;
    }

    private void oublierPhoto() {
        if (photoUri != null) {
            try {
                getContentResolver().delete(photoUri, null, null);
            } catch (Exception ignore) {
                // déjà supprimée
            }
            photoUri = null;
        }
    }

    @Override
    protected void onActivityResult(int code, int resultat, Intent donnees) {
        super.onActivityResult(code, resultat, donnees);
        if (code == CODE_FICHIER) {
            resultatChoix(resultat, donnees);
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

    /** Accessible depuis les pages SCOLARIS. */
    private class Pont {
        @JavascriptInterface
        public boolean autonome() {
            return true;
        }

        /** v2.2 — « Imprimer » des pages : gestionnaire d'impression d'Android (imprimante ou PDF). */
        @JavascriptInterface
        public void imprimer(final String titre) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Fichiers.imprimer(MainActivity.this, web, titre);
                }
            });
        }

        /** v2.2 — fichier reçu par la page (réponse d'un formulaire, document fabriqué dans la page). */
        @JavascriptInterface
        public void enregistrerFichier(final String nom, final String mime, final String base64) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    enregistrerDepuisPage(nom, mime, base64);
                }
            });
        }
    }
}
