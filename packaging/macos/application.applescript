on launchCloudra()
    set appPath to POSIX path of (path to me)
    set launcher to appPath & "Contents/MacOS/Cloudra"
    do shell script quoted form of launcher & " >/dev/null 2>&1 &"
end launchCloudra

on run
    launchCloudra()
end run

on reopen
    launchCloudra()
end reopen

on idle
    return 30
end idle

on quit
    set launcher to (POSIX path of (path to me)) & "Contents/MacOS/Cloudra"
    try
        do shell script quoted form of launcher & " stop"
    on error errorMessage
        display alert "Cloudra 未完全退出" message errorMessage as warning
    end try
    continue quit
end quit
