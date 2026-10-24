crashbackups stop
drc euclidean on
drc style drc(full)
drc off
gds read {image.gds}
load COLOR_IMAGE
select top cell
expand
drc on
drc check
drc catchup
set errors [drc listall why]
set file [open {magic_drc.txt} w]
puts $file "Magic drc(full): density and antenna excluded"
puts $file "Error categories: [expr {[llength $errors]/2}]"
puts $file $errors
close $file
quit -noprompt
