-- Dossiary launcher: opens the dossiary.html next to this app in Chrome or Edge,
-- the browsers whose folder access Dossiary needs. Built by build-launcher.sh.
on run
	set appPath to POSIX path of (path to me)
	set folderPath to do shell script "dirname " & quoted form of appPath
	set htmlPath to folderPath & "/dossiary.html"
	try
		do shell script "test -f " & quoted form of htmlPath
	on error
		display dialog "dossiary.html was not found next to Dossiary.app. Expected: " & htmlPath buttons {"OK"} default button "OK" with icon stop with title "Dossiary"
		return
	end try
	repeat with bundleId in {"com.google.Chrome", "com.microsoft.edgemac"}
		try
			do shell script "open -b " & bundleId & " " & quoted form of htmlPath
			return
		end try
	end repeat
	display dialog "Dossiary needs Google Chrome or Microsoft Edge." buttons {"OK"} default button "OK" with icon stop with title "Dossiary"
end run
