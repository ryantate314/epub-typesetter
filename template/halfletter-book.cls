\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{halfletter-book}[2026/07/16 v1.0 Half-letter trim book class for folded-folio booklet printing]

\DeclareOption*{\PassOptionsToClass{\CurrentOption}{scrbook}}
\ProcessOptions\relax

\LoadClass[fontsize=10pt,twoside,open=right,parskip=half,cleardoublepage=empty]{scrbook}

% ------------------------------------------------------------------
% Page geometry: 5.5 x 8.5in trim (half of US Letter, folded folio).
% Inner margin is generous for the fold; page numbers live on the
% outer edge where they're easiest to find while flipping pages.
% ------------------------------------------------------------------
\RequirePackage{geometry}
\geometry{
  paperwidth=5.5in,
  paperheight=8.5in,
  inner=0.8in,
  outer=0.55in,
  top=0.7in,
  bottom=0.75in,
  headsep=0.28in,
  footskip=0.35in,
}

% ------------------------------------------------------------------
% Fonts (requires XeLaTeX or LuaLaTeX).
% ------------------------------------------------------------------
\RequirePackage{fontspec}
\setmainfont{TeX Gyre Pagella}
\RequirePackage{microtype}

% ------------------------------------------------------------------
% Chapter opening drop caps.
% ------------------------------------------------------------------
\RequirePackage{lettrine}
\setcounter{DefaultLines}{2}
\renewcommand{\LettrineFontHook}{\normalfont}

% ------------------------------------------------------------------
% Running headers/footers: chapter title toward the inner margin,
% page number toward the outer margin. Chapter-opening pages get
% the plain style automatically (KOMA default).
% ------------------------------------------------------------------
\RequirePackage[automark]{scrlayer-scrpage}
\pagestyle{scrheadings}
\clearpairofpagestyles
\automark[chapter]{chapter}
\ihead{\headmark}
\ohead{\pagemark}
\cfoot{}

% ------------------------------------------------------------------
% Title page: match the serif body text rather than KOMA's default
% sans-bold display font, for a traditional book look.
% ------------------------------------------------------------------
\setkomafont{title}{\normalfont\bfseries\LARGE}
\setkomafont{author}{\normalfont\large}
\setkomafont{date}{\normalfont}
