package bj.memp.cp;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.MimeTypeMap;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.HashMap;
import java.util.Map;

/**
 * Applications web du MEMP pour Android (Application CP, CS Pobè, Mon école…) : même programme pour toutes,
 * seuls le nom, l'identifiant et le contenu de assets/www changent (flux GitHub « Fabriquer les applications »).
 * L'application web est embarquée dans l'APK (assets/www) et servie à l'adresse sécurisée
 * https://appassets.androidplatform.net/ (caméra, base de données locale) : elle fonctionne sans Internet.
 * Les exports (PDF, Excel, sauvegardes) sont enregistrés dans « Téléchargements » ; l'impression passe par Android.
 * Documents : « Télécharger en PDF », « Télécharger en Word » et « Imprimer » (js/doc-export.js dans les applications) ;
 * l'impression passe par le service d'impression d'Android.
 * Conception : Maître Aimé FACHOLA.
 */
public class MainActivity extends Activity {

    private static final String HOTE = "appassets.androidplatform.net";
    private static final String ACCUEIL = "https://" + HOTE + "/www/index.html";
    private static final int CODE_FICHIER = 41;
    private static final int CODE_STOCKAGE = 42;
    private static final int CODE_CAMERA = 43;
    private static final int CODE_CAMERA_FICHIER = 44;

    private WebView web;
    private ValueCallback<Uri[]> rappelFichier;
    private WebChromeClient.FileChooserParams paramsEnAttente;
    private PermissionRequest demandeCamera;
    private Uri photoUri;
    private String[] enregistrementEnAttente;
    private String nomAppli = "MEMP CP";

    /** Petit script ajouté à chaque page : téléchargements (liens « download » et blob:) et impression. */
    private static final String PONT_JS =
            "(function(){if(window.__mempPont)return;window.__mempPont=1;"
            // les fichiers créés par la page (Excel, PDF…) sont gardés le temps de les enregistrer : plus de fichier
            // vide quand la page libère l'adresse « blob: » avant qu'Android ait fini de la lire
            + "var memo={},co=URL.createObjectURL,ro=URL.revokeObjectURL;"
            + "URL.createObjectURL=function(o){var u=co.apply(URL,arguments);try{if(o instanceof Blob)memo[u]=o;}catch(x){}return u;};"
            + "URL.revokeObjectURL=function(u){setTimeout(function(){delete memo[u];ro.call(URL,u);},120000);};"
            + "function lire(b,nom){var f=new FileReader();"
            + "f.onload=function(){var d=String(f.result);MempCP.enregistrer(nom||'document',b.type||'',d.substring(d.indexOf(',')+1));};"
            + "f.onerror=function(){alert('Enregistrement impossible : fichier illisible');};f.readAsDataURL(b);}"
            + "function envoyer(href,nom){if(memo[href]){lire(memo[href],nom);return;}"
            + "fetch(href).then(function(r){return r.blob();}).then(function(b){lire(b,nom);}).catch(function(e){alert('Enregistrement impossible : '+e);});}"
            // lien créé puis cliqué par programme (même sans être placé dans la page)
            + "var clic=HTMLAnchorElement.prototype.click;HTMLAnchorElement.prototype.click=function(){var h=this.getAttribute('href')||'';"
            + "if(this.hasAttribute('download')&&(h.indexOf('blob:')===0||h.indexOf('data:')===0)){envoyer(this.href,this.getAttribute('download'));return;}return clic.apply(this,arguments);};"
            + "document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[download]');"
            + "if(!a)return;var h=a.getAttribute('href')||'';if(h.indexOf('blob:')===0||h.indexOf('data:')===0){e.preventDefault();e.stopPropagation();envoyer(a.href,a.getAttribute('download'));}},true);"
            // impression : les applications proposent PDF / Word / Imprimer (DocExport) ; sinon impression Android de la page
            + "if(!window.DocExport){window.print=function(){MempCP.imprimer(document.title||'MEMP CP');};}"
            // fenêtre d'impression (window.open('') puis document.write, comme ÉduGestion Pro) : imprimée par Android
            + "var ouvrir=window.open;window.open=function(u){u=String(u||'');"
            + "if(u.indexOf('blob:')===0||u.indexOf('data:')===0){envoyer(u,'document');return {closed:false,close:function(){},focus:function(){}};}"
            + "if(u&&u!=='about:blank'){return ouvrir.apply(window,arguments);}"
            + "var buf='',w={closed:false,focus:function(){},close:function(){w.closed=true;},"
            + "document:{open:function(){buf='';},write:function(t){buf+=t;},writeln:function(t){buf+=t+'\\n';},close:function(){}},"
            + "print:function(){var m=/<title>([^<]*)<\\/title>/i.exec(buf),t=m?m[1]:(document.title||'Document');"
            + "if(window.DocExport&&DocExport.choisirDocument){DocExport.choisirDocument(buf,t);}else{MempCP.imprimerHtml(t,buf);}}};return w;};"
            + "})();";

    @Override
    protected void onCreate(Bundle etat) {
        super.onCreate(etat);
        try {
            nomAppli = getApplicationInfo().loadLabel(getPackageManager()).toString();
        } catch (Exception ignore) {
            // nom par défaut
        }
        WebView.setWebContentsDebuggingEnabled(false);
        web = new WebView(this);
        if (nouvelleVersion()) {
            web.clearCache(true);   // pas d'anciens fichiers de la version précédente
        }
        WebSettings r = web.getSettings();
        r.setJavaScriptEnabled(true);
        r.setDomStorageEnabled(true);
        r.setDatabaseEnabled(true);
        r.setAllowFileAccess(false);
        r.setAllowContentAccess(true);
        r.setLoadWithOverviewMode(true);
        r.setUseWideViewPort(true);
        r.setBuiltInZoomControls(true);
        r.setDisplayZoomControls(false);
        r.setMediaPlaybackRequiresUserGesture(false);
        r.setSupportMultipleWindows(false);
        r.setUserAgentString(r.getUserAgentString() + " MempWeb-Android/1.0");
        web.addJavascriptInterface(new Pont(), "MempCP");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView vue, WebResourceRequest demande) {
                Uri u = demande.getUrl();
                if (!HOTE.equals(u.getHost())) {
                    return null;
                }
                return fichierEmbarque(u.getPath());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView vue, WebResourceRequest demande) {
                Uri u = demande.getUrl();
                if (HOTE.equals(u.getHost())) {
                    return false;
                }
                try {   // WhatsApp, téléphone, e-mail, sites : applications du téléphone
                    if ("intent".equals(u.getScheme())) {
                        Intent i = Intent.parseUri(u.toString(), Intent.URI_INTENT_SCHEME);
                        i.addCategory(Intent.CATEGORY_BROWSABLE);
                        i.setComponent(null);
                        i.setSelector(null);
                        try {
                            startActivity(i);
                        } catch (ActivityNotFoundException e2) {
                            String repli = i.getStringExtra("browser_fallback_url");
                            if (repli != null) {
                                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(repli)));
                            } else {
                                throw e2;
                            }
                        }
                    } else {
                        startActivity(new Intent(Intent.ACTION_VIEW, u));
                    }
                } catch (ActivityNotFoundException | java.net.URISyntaxException e) {
                    Toast.makeText(MainActivity.this, "Aucune application pour ouvrir ce lien", Toast.LENGTH_SHORT).show();
                }
                return true;
            }

            @Override
            public void onPageFinished(WebView vue, String url) {
                vue.evaluateJavascript(PONT_JS, null);
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView vue, ValueCallback<Uri[]> rappel, FileChooserParams params) {
                return ouvrirChoixFichier(rappel, params);
            }

            @Override
            public void onPermissionRequest(final PermissionRequest demande) {
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

        setContentView(web);
        if (etat != null) {
            web.restoreState(etat);
        } else {
            web.loadUrl(ACCUEIL);
        }
    }

    /** Vrai juste après l'installation ou une mise à jour de l'application. */
    private boolean nouvelleVersion() {
        try {
            PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
            String tampon = info.versionCode + "-" + info.lastUpdateTime;
            SharedPreferences prefs = getSharedPreferences("mempcp", Context.MODE_PRIVATE);
            if (!tampon.equals(prefs.getString("version", ""))) {
                prefs.edit().putString("version", tampon).apply();
                return true;
            }
        } catch (PackageManager.NameNotFoundException ignore) {
            // sans importance
        }
        return false;
    }

    private static final Map<String, String> TYPES = new HashMap<>();

    static {
        TYPES.put("html", "text/html");
        TYPES.put("js", "text/javascript");
        TYPES.put("mjs", "text/javascript");
        TYPES.put("css", "text/css");
        TYPES.put("json", "application/json");
        TYPES.put("webmanifest", "application/manifest+json");
        TYPES.put("svg", "image/svg+xml");
        TYPES.put("png", "image/png");
        TYPES.put("jpg", "image/jpeg");
        TYPES.put("jpeg", "image/jpeg");
        TYPES.put("ico", "image/x-icon");
        TYPES.put("pdf", "application/pdf");
        TYPES.put("ttf", "font/ttf");
        TYPES.put("woff", "font/woff");
        TYPES.put("woff2", "font/woff2");
        TYPES.put("txt", "text/plain");
        TYPES.put("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        TYPES.put("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
    }

    /** Fichier de l'application embarqué dans l'APK (assets/www/...). */
    private WebResourceResponse fichierEmbarque(String chemin) {
        if (chemin == null || chemin.equals("/") || chemin.isEmpty()) {
            chemin = "/www/index.html";
        }
        if (chemin.endsWith("/")) {
            chemin = chemin + "index.html";
        }
        String rel = chemin.startsWith("/") ? chemin.substring(1) : chemin;
        if (rel.contains("..")) {
            return new WebResourceResponse("text/plain", "utf-8", 403, "Interdit", null, null);
        }
        String ext = rel.contains(".") ? rel.substring(rel.lastIndexOf('.') + 1).toLowerCase() : "";
        String type = TYPES.get(ext);
        if (type == null) {
            type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
        }
        if (type == null) {
            type = "application/octet-stream";
        }
        try {
            InputStream in = getAssets().open(rel);
            Map<String, String> entetes = new HashMap<>();
            entetes.put("Cache-Control", "no-cache");
            entetes.put("Access-Control-Allow-Origin", "*");
            String enc = type.startsWith("text/") || type.contains("json") || type.contains("javascript") ? "utf-8" : null;
            return new WebResourceResponse(type, enc, 200, "OK", entetes, in);
        } catch (IOException e) {
            return new WebResourceResponse("text/plain", "utf-8", 404, "Introuvable", null, null);
        }
    }

    // ------------------------------------------------------------------ enregistrement des exports
    private void enregistrer(String nom, String type, String base64) {
        if (Build.VERSION.SDK_INT < 29
                && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            enregistrementEnAttente = new String[]{nom, type, base64};
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, CODE_STOCKAGE);
            return;
        }
        try {
            byte[] octets = Base64.decode(base64, Base64.DEFAULT);
            String propre = nom.replaceAll("[\\\\/:*?\"<>|]", "_");
            if (type == null || type.isEmpty() || type.startsWith("application/octet-stream")) {
                String ext = android.webkit.MimeTypeMap.getFileExtensionFromUrl(propre.replace(' ', '_')).toLowerCase();
                String devine = android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
                if ("xlsx".equals(ext)) devine = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
                if ("docx".equals(ext)) devine = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
                if ("pdf".equals(ext)) devine = "application/pdf";
                if ("json".equals(ext) || "scsync".equals(ext)) devine = "application/json";
                type = devine != null ? devine : "application/octet-stream";
            }
            if (Build.VERSION.SDK_INT >= 29) {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Downloads.DISPLAY_NAME, propre);
                v.put(MediaStore.Downloads.MIME_TYPE, type);
                v.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/" + dossierExports());
                Uri u = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                if (u == null) {
                    throw new IOException("emplacement refusé");
                }
                try (OutputStream out = getContentResolver().openOutputStream(u)) {
                    out.write(octets);
                }
                ouvrir(u, type);
            } else {
                File dossier = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), dossierExports());
                dossier.mkdirs();
                File f = new File(dossier, propre);
                try (OutputStream out = new FileOutputStream(f)) {
                    out.write(octets);
                }
            }
            Toast.makeText(this, "Enregistré dans Téléchargements / " + dossierExports() + " : " + propre, Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Toast.makeText(this, "Enregistrement impossible : " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private String dossierExports() {
        return nomAppli.replaceAll("[\\\\/:*?\"<>|]", "_");
    }

    private void ouvrir(Uri u, String type) {
        try {
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(u, type);
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(i, "Ouvrir le fichier"));
        } catch (Exception ignore) {
            // pas d'application pour ce type : le fichier reste dans Téléchargements
        }
    }

    /** Page HTML écrite par l'application (fenêtre d'impression) : chargée dans une vue à part, puis imprimée. */
    private WebView vueImpression;
    private void imprimerHtml(final String titre, String html) {
        final WebView v = new WebView(this);
        vueImpression = v;   // gardée jusqu'à la fin de l'impression
        v.getSettings().setJavaScriptEnabled(false);
        v.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView vue, WebResourceRequest demande) {
                Uri u = demande.getUrl();
                return HOTE.equals(u.getHost()) ? fichierEmbarque(u.getPath()) : null;
            }

            @Override
            public void onPageFinished(WebView vue, String url) {
                PrintManager pm = (PrintManager) getSystemService(Context.PRINT_SERVICE);
                if (pm != null) {
                    pm.print(titre, vue.createPrintDocumentAdapter(titre), new PrintAttributes.Builder().build());
                }
            }
        });
        v.loadDataWithBaseURL("https://" + HOTE + "/www/", html, "text/html", "UTF-8", null);
    }

    private void imprimer(String titre) {
        PrintManager pm = (PrintManager) getSystemService(Context.PRINT_SERVICE);
        if (pm != null) {
            pm.print(titre, web.createPrintDocumentAdapter(titre), new PrintAttributes.Builder().build());
        }
    }

    // ------------------------------------------------------------------ photos (appareil photo ou galerie)
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

    /** Intention de choix de fichier : les extensions demandées (.xlsx, .json, .scsync…) deviennent des types MIME. */
    private Intent intentionFichier(WebChromeClient.FileChooserParams params) {
        Intent i = new Intent(Intent.ACTION_GET_CONTENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        java.util.ArrayList<String> mimes = new java.util.ArrayList<>();
        boolean tout = false;
        String[] types = params.getAcceptTypes();
        if (types != null) {
            for (String brut : types) {
                if (brut == null) continue;
                for (String t : brut.split(",")) {
                    t = t.trim().toLowerCase();
                    if (t.isEmpty()) continue;
                    if (t.startsWith(".")) {
                        String ext = t.substring(1);
                        String m = TYPES.get(ext);
                        if (m == null) m = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
                        if ("xls".equals(ext)) m = "application/vnd.ms-excel";
                        if ("csv".equals(ext)) m = "text/csv";
                        if (m == null) { tout = true; } else if (!mimes.contains(m)) { mimes.add(m); }
                        if ("csv".equals(ext) && !mimes.contains("text/comma-separated-values")) mimes.add("text/comma-separated-values");
                    } else if (t.contains("/")) {
                        if (!mimes.contains(t)) mimes.add(t);
                    } else {
                        tout = true;
                    }
                }
            }
        }
        if (tout || mimes.isEmpty()) {
            i.setType("*/*");   // extension propre à l'application (.scsync…) : tous les fichiers
        } else if (mimes.size() == 1) {
            i.setType(mimes.get(0));
        } else {
            i.setType("*/*");
            i.putExtra(Intent.EXTRA_MIME_TYPES, mimes.toArray(new String[0]));
        }
        if (params.getMode() == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
            i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        }
        return i;
    }

    private boolean lancerChoix(WebChromeClient.FileChooserParams params, boolean image) {
        Intent galerie = intentionFichier(params);
        Intent aLancer = galerie;
        photoUri = null;
        if (image && checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            Intent photo = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
            try {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Images.Media.DISPLAY_NAME, "photo_" + System.currentTimeMillis() + ".jpg");
                v.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                if (Build.VERSION.SDK_INT >= 29) {
                    v.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/" + dossierExports());
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
        if (code != CODE_FICHIER) {
            return;
        }
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

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] resultats) {
        super.onRequestPermissionsResult(code, permissions, resultats);
        boolean ok = resultats.length > 0 && resultats[0] == PackageManager.PERMISSION_GRANTED;
        if (code == CODE_CAMERA_FICHIER) {
            WebChromeClient.FileChooserParams p = paramsEnAttente;
            paramsEnAttente = null;
            if (p != null) {
                lancerChoix(p, true);
            }
        } else if (code == CODE_CAMERA && demandeCamera != null) {
            if (ok) {
                demandeCamera.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
            } else {
                demandeCamera.deny();
            }
            demandeCamera = null;
        } else if (code == CODE_STOCKAGE && enregistrementEnAttente != null) {
            String[] t = enregistrementEnAttente;
            enregistrementEnAttente = null;
            if (ok) {
                enregistrer(t[0], t[1], t[2]);
            }
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle etat) {
        super.onSaveInstanceState(etat);
        if (web != null) {
            web.saveState(etat);
        }
    }

    /** Retour : ferme d'abord la fenêtre (boîte de dialogue) ouverte dans l'application, sinon page précédente. */
    private static final String JS_RETOUR = "(function(){var s='.de-voile,.ped-voile,.uas-voile,.pvs-voile,.gd-voile,.modal.active,.modal.show,.modal.open,.modal-overlay.active,[role=dialog][aria-modal=true]';"
            + "var v=[].slice.call(document.querySelectorAll(s)).filter(function(e){var r=e.getBoundingClientRect();return r.width>0&&r.height>0;});"
            + "if(!v.length)return '';var e=v[v.length-1];var b=e.querySelector('[data-de=annuler],header button[aria-label=Fermer],.modal-close,.close,[data-dismiss],[aria-label=Fermer]');"
            + "if(b){b.click();return 'ferme';}var k=new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true});document.dispatchEvent(k);return 'ferme';})()";

    @Override
    public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        web.evaluateJavascript(JS_RETOUR, new ValueCallback<String>() {
            @Override
            public void onReceiveValue(String r) {
                if (r != null && r.contains("ferme")) {
                    return;
                }
                if (web.canGoBack()) {
                    web.goBack();
                } else {
                    MainActivity.super.onBackPressed();
                }
            }
        });
    }

    /** Appelé depuis les pages de l'application (script PONT_JS). */
    private class Pont {
        @JavascriptInterface
        public void enregistrer(final String nom, final String type, final String base64) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    MainActivity.this.enregistrer(nom, type, base64);
                }
            });
        }

        @JavascriptInterface
        public void imprimer(final String titre) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    MainActivity.this.imprimer(titre);
                }
            });
        }

        @JavascriptInterface
        public void imprimerHtml(final String titre, final String html) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    MainActivity.this.imprimerHtml(titre, html);
                }
            });
        }

        @JavascriptInterface
        public boolean android() {
            return true;
        }
    }
}
