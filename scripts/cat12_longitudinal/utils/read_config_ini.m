function config = read_config_ini(file_path)
    config = struct();
    if ~exist(file_path, 'file'), return; end
    
    fid = fopen(file_path, 'r');
    current_section = '';
    
    while ~feof(fid)
        line = strtrim(fgetl(fid));
        if isempty(line) || line(1) == '#' || line(1) == ';', continue; end
        
        if line(1) == '[' && line(end) == ']'
            current_section = line(2:end-1);
            % Create section struct if it doesn't exist
            if ~isfield(config, lower(current_section))
                config.(lower(current_section)) = struct();
            end
        elseif ~isempty(strfind(line, '='))
            parts = strsplit(line, '=');
            key = strtrim(parts{1});
            val = strtrim(strjoin(parts(2:end), '='));
            
            % Try to convert to number
            num_val = str2double(val);
            if ~isnan(num_val)
                val = num_val;
            elseif strcmpi(val, 'true')
                val = true;
            elseif strcmpi(val, 'false')
                val = false;
            end
            
            if ~isempty(current_section)
                config.(lower(current_section)).(lower(key)) = val;
            else
                config.(lower(key)) = val;
            end
        end
    end
    fclose(fid);
end
