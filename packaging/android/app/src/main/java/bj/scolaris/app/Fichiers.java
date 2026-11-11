package bj.scolaris.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.provider.MediaStore;
import android.webkit.CookieManager;
import android.webkit.MimeTypeMap;
import android.webkit.WebView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLDecoder;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * v2.2 — Fichiers téléchargés depuis les pages SCOLARIS (PDF, Word, Excel, ZIP, sauvegardes) :
 * enregistrés dans « Téléchargements / SCOLARIS » avec leur vrai nom (accents compris), puis
 * proposés à l'ouverture ou au partage (WhatsApp, e-mail…). Impression par le gestionnaire
 * d'impression d'Android (imprimante ou « Enregistrer au format PDF »).
 * Copie identique dans packaging/android (application SCOLARIS reliée au serveur) : seul le paquet change.
 */
final class Fichiers {

    private Fichiers() {
    }

    interface Fin {
        void fini(Uri uri, String nom, String mime, String erreur);
    }

    private static final Pattern NOM_UTF8 = Pattern.compile("filename\\*\\s*=\\s*(?:UTF-8|utf-8)''([^;]+)");
    private static final Pattern NOM_SIMPLE = Pattern.compile("filename\\s*=\\s*\"?([^\";]+)\"?");

    /** Nom du fichier d'après l'en-tête Content-Disposition (forme UTF-8 d'abord), sinon d'après l'adresse. */
    static String nomFichier(String disposition, String url, String mime) {
        String nom = null;
        if (disposition != null) {
            Matcher m = NOM_UTF8.matcher(disposition);
            if (m.find()) {
                try {
                    nom = URLDecoder.decode(m.group(1).trim(), "UTF-8");
                } catch (Exception ignore) {
                    nom = null;
                }
            }
            if (nom == null) {
                m = NOM_SIMPLE.matcher(disposition);
                if (m.find()) {
                    nom = m.group(1).trim();
                }
            }
        }
        if (nom == null || nom.isEmpty()) {
            String chemin = Uri.parse(url).getLastPathSegment();
            nom = chemin == null || chemin.isEmpty() ? "document" : chemin;
        }
        nom = nom.replaceAll("[\\\\/:*?\"<>|]", "_");
        if (nom.indexOf('.') < 0) {
            String ext = mime == null ? null : MimeTypeMap.getSingleton().getExtensionFromMimeType(mime);
            if (ext != null) {
                nom = nom + "." + ext;
            }
        }
        return nom;
    }

    static String typeDe(String nom, String mime) {
        if (mime != null && !mime.isEmpty() && !mime.startsWith("application/octet-stream")) {
            int p = mime.indexOf(';');
            return p > 0 ? mime.substring(0, p).trim() : mime.trim();
        }
        int i = nom.lastIndexOf('.');
        String ext = i >= 0 ? nom.substring(i + 1).toLowerCase() : "";
        String t = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
        if (t == null && "docx".equals(ext)) {
            t = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
        }
        return t == null ? "application/octet-stream" : t;
    }

    /** true quand Android (avant la version 10) demande d'abord l'autorisation d'écrire dans Téléchargements. */
    static boolean autorisationNecessaire(Activity a) {
        return Build.VERSION.SDK_INT < 29
                && a.checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != android.content.pm.PackageManager.PERMISSION_GRANTED;
    }

    /** Écrit les octets dans Téléchargements / SCOLARIS et renvoie une adresse que les autres applications peuvent ouvrir. */
    static void enregistrer(final Activity a, final String nom, final String mime, final InputStream flux, final Fin fin) {
        final String type = typeDe(nom, mime);
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                ContentResolver cr = a.getContentResolver();
                ContentValues v = new ContentValues();
                v.put(MediaStore.MediaColumns.DISPLAY_NAME, nom);
                v.put(MediaStore.MediaColumns.MIME_TYPE, type);
                v.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/SCOLARIS");
                v.put(MediaStore.MediaColumns.IS_PENDING, 1);
                Uri uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                if (uri == null) {
                    throw new IOException("Téléchargements indisponible");
                }
                OutputStream out = cr.openOutputStream(uri);
                try {
                    copier(flux, out);
                } finally {
                    if (out != null) {
                        out.close();
                    }
                }
                ContentValues fini = new ContentValues();
                fini.put(MediaStore.MediaColumns.IS_PENDING, 0);
                cr.update(uri, fini, null, null);
                terminer(a, fin, uri, nom, type, null);
            } else {
                File dossier = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "SCOLARIS");
                if (!dossier.isDirectory() && !dossier.mkdirs()) {
                    throw new IOException("dossier Téléchargements introuvable");
                }
                File f = new File(dossier, nom);
                int k = 1;
                int point = nom.lastIndexOf('.');
                while (f.exists()) {
                    f = new File(dossier, point > 0 ? nom.substring(0, point) + " (" + k + ")" + nom.substring(point) : nom + " (" + k + ")");
                    k++;
                }
                OutputStream out = new FileOutputStream(f);
                try {
                    copier(flux, out);
                } finally {
                    out.close();
                }
                final String nomFinal = f.getName();
                MediaScannerConnection.scanFile(a, new String[]{f.getAbsolutePath()}, new String[]{type},
                        new MediaScannerConnection.OnScanCompletedListener() {
                            @Override
                            public void onScanCompleted(String chemin, Uri uri) {
                                terminer(a, fin, uri, nomFinal, type, null);
                            }
                        });
            }
        } catch (Exception e) {
            terminer(a, fin, null, nom, type, e.getMessage() == null ? e.toString() : e.getMessage());
        } finally {
            try {
                flux.close();
            } catch (Exception ignore) {
                // déjà fermé
            }
        }
    }

    private static void terminer(Activity a, final Fin fin, final Uri uri, final String nom, final String type, final String erreur) {
        a.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                fin.fini(uri, nom, type, erreur);
            }
        });
    }

    private static void copier(InputStream in, OutputStream out) throws IOException {
        byte[] tampon = new byte[32768];
        int n;
        while ((n = in.read(tampon)) > 0) {
            out.write(tampon, 0, n);
        }
    }

    /** Téléchargement d'une adresse de l'application (GET, avec la session de la page). Se fait en arrière-plan. */
    static void telecharger(final Activity a, final String url, final String userAgent, final String disposition,
                            final String mime, final Fin fin) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection c = null;
                try {
                    c = (HttpURLConnection) new URL(url).openConnection();
                    c.setConnectTimeout(30000);
                    c.setReadTimeout(180000);
                    String cookies = CookieManager.getInstance().getCookie(url);
                    if (cookies != null) {
                        c.setRequestProperty("Cookie", cookies);
                    }
                    if (userAgent != null) {
                        c.setRequestProperty("User-Agent", userAgent);
                    }
                    c.setRequestProperty("Accept-Encoding", "identity");
                    int code = c.getResponseCode();
                    if (code >= 400) {
                        throw new IOException("réponse " + code + " du serveur");
                    }
                    String d = c.getHeaderField("Content-Disposition");
                    String t = c.getContentType();
                    String nom = nomFichier(d != null ? d : disposition, url, t != null ? t : mime);
                    enregistrer(a, nom, t != null ? t : mime, c.getInputStream(), fin);
                } catch (Exception e) {
                    terminer(a, fin, null, nomFichier(disposition, url, mime), mime, e.getMessage() == null ? e.toString() : e.getMessage());
                } finally {
                    if (c != null) {
                        c.disconnect();
                    }
                }
            }
        }, "telechargement").start();
    }

    /** Fenêtre « Enregistré dans Téléchargements » : ouvrir, partager ou fermer. */
    static void proposer(final Activity a, final Uri uri, final String nom, final String type, String erreur) {
        if (erreur != null || uri == null) {
            Toast.makeText(a, "Téléchargement impossible : " + (erreur == null ? "fichier introuvable" : erreur), Toast.LENGTH_LONG).show();
            return;
        }
        if (a.isFinishing()) {
            return;
        }
        new AlertDialog.Builder(a)
                .setTitle("Fichier enregistré")
                .setMessage(nom + "\n\nDossier : Téléchargements / SCOLARIS")
                .setPositiveButton("Ouvrir", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        Intent i = new Intent(Intent.ACTION_VIEW);
                        i.setDataAndType(uri, type);
                        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                        try {
                            a.startActivity(Intent.createChooser(i, "Ouvrir avec"));
                        } catch (ActivityNotFoundException e) {
                            Toast.makeText(a, "Aucune application pour ouvrir ce fichier (installez un lecteur PDF ou Word)", Toast.LENGTH_LONG).show();
                        }
                    }
                })
                .setNeutralButton("Partager", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        Intent i = new Intent(Intent.ACTION_SEND);
                        i.setType(type);
                        i.putExtra(Intent.EXTRA_STREAM, uri);
                        i.putExtra(Intent.EXTRA_SUBJECT, nom);
                        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        try {
                            a.startActivity(Intent.createChooser(i, "Partager « " + nom + " »"));
                        } catch (ActivityNotFoundException e) {
                            Toast.makeText(a, "Aucune application de partage", Toast.LENGTH_SHORT).show();
                        }
                    }
                })
                .setNegativeButton("Fermer", null)
                .show();
    }

    /** Impression de la page affichée (imprimante, ou « Enregistrer au format PDF » d'Android). */
    static void imprimer(Activity a, WebView w, String titre) {
        if (w == null) {
            return;
        }
        try {
            PrintManager pm = (PrintManager) a.getSystemService(Context.PRINT_SERVICE);
            String t = titre == null || titre.isEmpty() ? "SCOLARIS" : titre;
            PrintDocumentAdapter ad = w.createPrintDocumentAdapter(t);
            pm.print(t, ad, new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());
        } catch (Exception e) {
            Toast.makeText(a, "Impression impossible : utilisez « Télécharger PDF »", Toast.LENGTH_LONG).show();
        }
    }
}
